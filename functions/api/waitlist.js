// POST /api/waitlist — lista de espera «Acceso Asesorías Pro» (modo validación). Se guarda en D1.
import { bumpQuota, clientKey, config, incrMetric, insertLead, json, todayMadrid } from "../../cloudflare/http.js";
import { LeadError, validateLead } from "../../cloudflare/leads.js";

const OK = { ok: true, mensaje: "¡Gracias! Te escribiremos por orden de solicitud. No se te cobrará nada ahora." };

export async function onRequestPost({ request, env }) {
  const cfg = config(env);
  const today = todayMadrid();
  if (env.DB && (await bumpQuota(env.DB, await clientKey(request, cfg.ipSalt, today, "form"), today)) > 30)
    return json({ detail: "Demasiados envíos desde tu conexión hoy. Inténtalo mañana." }, 429);
  let payload;
  try {
    payload = await request.json();
  } catch (_) {
    return json({ detail: "Cuerpo JSON no válido." }, 422);
  }
  let lead;
  try {
    lead = validateLead(payload || {});
  } catch (error) {
    if (error instanceof LeadError) return json({ detail: error.message }, 422);
    throw error;
  }
  if (lead && env.DB) {
    await insertLead(env.DB, lead, new Date().toISOString());
    await incrMetric(env.DB, today, `lead_${lead.origen_clic}`);
  }
  return json(OK, 201); // los bots (campo trampa) reciben la misma respuesta y no se guardan
}
