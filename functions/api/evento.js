// POST /api/evento — contador diario agregado (sin cookies ni identificadores) para medir el embudo.
import { EVENTOS_CLIENTE } from "../../cloudflare/constants.js";
import { bumpQuota, clientKey, config, incrMetric, json, todayMadrid } from "../../cloudflare/http.js";

export async function onRequestPost({ request, env }) {
  let tipo;
  try {
    tipo = (await request.json()).tipo;
  } catch (_) {
    tipo = undefined;
  }
  if (!EVENTOS_CLIENTE.includes(tipo)) return json({ detail: "Evento no reconocido." }, 422);
  const today = todayMadrid();
  if (env.DB) {
    const cfg = config(env);
    if ((await bumpQuota(env.DB, await clientKey(request, cfg.ipSalt, today, "evento"), today)) > 500) return json(null, 204);
    await incrMetric(env.DB, today, tipo);
  }
  return json(null, 204);
}
