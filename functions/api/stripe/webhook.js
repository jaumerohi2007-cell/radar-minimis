// POST /api/stripe/webhook — opcional (requiere el secreto STRIPE_WEBHOOK_SECRET): aplica al instante bajas y
// cambios de estado de la suscripción. Sin webhook, la licencia se revalida contra Stripe cada 12 h.
import { CSQL } from "../../../cloudflare/cuentas.js";
import { json } from "../../../cloudflare/http.js";
import { ACTIVE_STATUSES, StripeError, verifyWebhook } from "../../../cloudflare/stripe.js";

const SUBSCRIPTION_EVENTS = new Set(["customer.subscription.updated", "customer.subscription.deleted", "customer.subscription.paused", "customer.subscription.resumed"]);

export async function onRequestPost({ request, env }) {
  if (!env.STRIPE_WEBHOOK_SECRET) return json({ detail: "Webhook no configurado." }, 503);
  let event;
  try {
    event = await verifyWebhook(await request.text(), request.headers.get("Stripe-Signature"), env.STRIPE_WEBHOOK_SECRET);
  } catch (error) {
    if (error instanceof StripeError || error instanceof SyntaxError) return json({ detail: "Firma no válida." }, 400);
    throw error;
  }
  if (SUBSCRIPTION_EVENTS.has(event.type) && env.DB) {
    const sub = event.data?.object || {};
    const status = event.type === "customer.subscription.deleted" ? "canceled" : String(sub.status || "");
    await env.DB.prepare(CSQL.estadoPorSuscripcion).bind(status, ACTIVE_STATUSES.has(status) ? 1 : 0, new Date().toISOString(), sub.id).run();
  }
  return json({ recibido: true });
}
