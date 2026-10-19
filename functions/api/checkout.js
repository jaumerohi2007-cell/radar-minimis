// POST /api/checkout — crea una sesión de Stripe Checkout (suscripción mensual del plan Asesorías Pro).
import { ORIGENES, PLAN } from "../../cloudflare/constants.js";
import { LEGAL_ENTITY, classifyNif, normalize } from "../../cloudflare/core.js";
import { bumpQuota, clientKey, config, incrMetric, json, todayMadrid } from "../../cloudflare/http.js";
import { StripeError, createCheckoutSession } from "../../cloudflare/stripe.js";

export async function onRequestPost({ request, env }) {
  const cfg = config(env);
  if (cfg.billingMode !== "stripe") return json({ detail: "Los pagos no están activados (BILLING_MODE=validation)." }, 404);
  const today = todayMadrid();
  if (env.DB && (await bumpQuota(env.DB, await clientKey(request, cfg.ipSalt, today, "checkout"), today)) > 20)
    return json({ detail: "Demasiados intentos de pago desde tu conexión hoy. Inténtalo mañana." }, 429);
  let payload;
  try {
    payload = (await request.json()) || {};
  } catch (_) {
    payload = {};
  }
  const origen = ORIGENES.includes(payload.origen) ? payload.origen : "plan";
  const cif = normalize(payload.cif);
  try {
    const session = await createCheckoutSession(env, { siteUrl: cfg.siteUrl, origen, cif: classifyNif(cif) === LEGAL_ENTITY ? cif : null });
    if (env.DB) await incrMetric(env.DB, today, `checkout_${origen}`);
    return json({ url: session.url, plan: PLAN.nombre, precio: PLAN.precio });
  } catch (error) {
    if (!(error instanceof StripeError)) throw error;
    console.error("checkout", error.status, error.code, error.message);
    return json({ detail: "No se pudo iniciar el pago con Stripe. Inténtalo de nuevo en unos minutos." }, 503);
  }
}
