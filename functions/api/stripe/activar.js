// POST /api/stripe/activar — tras el retorno de Checkout: verifica el pago en Stripe, crea la licencia en D1
// y devuelve la clave de acceso en claro (la base de datos solo guarda su SHA-256).
import { CuentaError, activate } from "../../../cloudflare/cuentas.js";
import { bumpQuota, clientKey, config, incrMetric, json, todayMadrid } from "../../../cloudflare/http.js";
import { StripeError } from "../../../cloudflare/stripe.js";

export async function onRequestPost({ request, env }) {
  if (!env.DB) return json({ detail: "Base de datos no disponible." }, 503);
  const cfg = config(env);
  const today = todayMadrid();
  if ((await bumpQuota(env.DB, await clientKey(request, cfg.ipSalt, today, "activar"), today)) > 30)
    return json({ detail: "Demasiados intentos desde tu conexión hoy." }, 429);
  let sessionId;
  try {
    sessionId = (await request.json()).session_id;
  } catch (_) {
    sessionId = undefined;
  }
  try {
    const result = await activate(env, sessionId);
    if (result.nueva) await incrMetric(env.DB, today, "alta_suscripcion");
    return json({ clave: result.clave, nueva: result.nueva, cuenta: result.cuenta }, result.nueva ? 201 : 200);
  } catch (error) {
    if (error instanceof CuentaError) return json({ detail: error.message }, error.status);
    if (error instanceof StripeError) {
      console.error("activar", error.status, error.code, error.message);
      if (error.status === 404) return json({ detail: "Stripe no reconoce esta sesión de pago." }, 404);
      return json({ detail: "No se pudo verificar el pago con Stripe. Recarga la página en unos minutos." }, 503);
    }
    throw error;
  }
}
