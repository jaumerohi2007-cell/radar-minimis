// POST /api/cuenta/portal — sesión del portal de cliente de Stripe (facturas, método de pago y baja).
// Admite también licencias inactivas: el portal es donde se reactiva la suscripción.
import { accountFrom } from "../../../cloudflare/cuentas.js";
import { config, json } from "../../../cloudflare/http.js";
import { StripeError, stripe } from "../../../cloudflare/stripe.js";

export async function onRequestPost({ request, env }) {
  const cuenta = await accountFrom(request, env);
  if (!cuenta) return json({ detail: "Clave de acceso no válida o ausente." }, 401);
  const contacto = env.RM_PRIVACY_EMAIL || env.CONTACT_EMAIL || "el email del aviso legal";
  if (!cuenta.stripe_customer) return json({ detail: `Escribe a ${contacto} para gestionar la suscripción.` }, 409);
  try {
    const session = await stripe(env, "POST", "/billing_portal/sessions", {
      customer: cuenta.stripe_customer,
      return_url: `${config(env).siteUrl}/asesorias/`,
    });
    return json({ url: session.url });
  } catch (error) {
    if (!(error instanceof StripeError)) throw error;
    console.error("portal", error.status, error.code, error.message);
    return json({ detail: `El portal de cliente no está disponible ahora. Para facturas o bajas escribe a ${contacto}.` }, 503);
  }
}
