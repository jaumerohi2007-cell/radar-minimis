// GET /api/health — estado del servicio. Con ?stripe=1 (modo stripe) comprueba la clave y el precio en Stripe;
// nunca devuelve la clave, solo si es «live» o «test» y el id público del precio.
import { PLAN, VERSION } from "../../cloudflare/constants.js";
import { config, json } from "../../cloudflare/http.js";
import { StripeError, resolvePrice, stripeMode } from "../../cloudflare/stripe.js";

export async function onRequestGet({ request, env }) {
  const cfg = config(env);
  const data = { ok: true, version: VERSION, modo: cfg.billingMode, runtime: "cloudflare-pages-functions", d1: Boolean(env.DB) };
  if (cfg.billingMode === "stripe" && new URL(request.url).searchParams.get("stripe") === "1") {
    data.stripe = { clave: stripeMode(env), plan: PLAN.nombre, precio: PLAN.precio, price_id: null, price_fijado: Boolean(env.STRIPE_PRICE_ID) };
    try {
      data.stripe.price_id = await resolvePrice(env);
    } catch (error) {
      if (!(error instanceof StripeError)) throw error;
      data.stripe.error = error.code || "stripe";
    }
  }
  return json(data);
}
