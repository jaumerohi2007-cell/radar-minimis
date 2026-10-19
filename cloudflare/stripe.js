// Cliente mínimo de la API de Stripe para Workers (fetch + application/x-www-form-urlencoded).
// La clave vive solo en el secreto STRIPE_SECRET_KEY de Cloudflare Pages: nunca en el repositorio ni en disco,
// y los mensajes de error de Stripe no se devuelven al navegador.
import { PLAN } from "./constants.js";

const API = "https://api.stripe.com/v1";
// Estados de suscripción que mantienen la licencia activa (past_due: periodo de gracia mientras Stripe reintenta).
export const ACTIVE_STATUSES = new Set(["active", "trialing", "past_due"]);

export class StripeError extends Error {
  constructor(message, status = 502, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** Aplana {a: {b: [x]}} a a[b][0]=x, el formato de parámetros de la API de Stripe. */
export function formEncode(params, prefix = "", out = new URLSearchParams()) {
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    const name = prefix ? `${prefix}[${key}]` : key;
    if (typeof value === "object") formEncode(value, name, out);
    else out.append(name, String(value));
  }
  return out;
}

export async function stripe(env, method, path, params) {
  if (!env.STRIPE_SECRET_KEY) throw new StripeError("Falta el secreto STRIPE_SECRET_KEY", 503, "sin_clave");
  const body = params ? formEncode(params) : null;
  const isGet = method === "GET";
  const resp = await fetch(isGet && body ? `${API}${path}?${body}` : `${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      ...(isGet ? {} : { "Content-Type": "application/x-www-form-urlencoded" }),
    },
    body: isGet ? undefined : body,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new StripeError(data.error?.message || `Stripe HTTP ${resp.status}`, resp.status, data.error?.code || "");
  return data;
}

export const stripeMode = (env) => (String(env.STRIPE_SECRET_KEY || "").startsWith("sk_live_") ? "live" : env.STRIPE_SECRET_KEY ? "test" : null);

let cachedPrice = null;
export const resetPriceCache = () => {
  cachedPrice = null;
};

/**
 * Precio del plan: STRIPE_PRICE_ID si está fijado; si no, el precio activo recurrente de PLAN.importe_cent €/mes
 * de un producto «Radar Minimis» (prioriza el nombre exacto del plan y, a igualdad, el más reciente).
 */
export async function resolvePrice(env) {
  if (env.STRIPE_PRICE_ID) return env.STRIPE_PRICE_ID;
  if (cachedPrice) return cachedPrice;
  const list = await stripe(env, "GET", "/prices", {
    active: "true",
    type: "recurring",
    currency: "eur",
    limit: 100,
    expand: ["data.product"],
  });
  const fits = (list.data || []).filter(
    (p) =>
      p.unit_amount === PLAN.importe_cent &&
      p.recurring?.interval === "month" &&
      (p.recurring.interval_count ?? 1) === 1 &&
      p.product &&
      typeof p.product === "object" &&
      p.product.active !== false &&
      /radar\s*minimis/i.test(p.product.name || ""),
  );
  fits.sort((a, b) => Number(b.product.name === PLAN.nombre) - Number(a.product.name === PLAN.nombre) || b.created - a.created);
  if (!fits.length) throw new StripeError(`No hay un precio activo de ${PLAN.precio} para «Radar Minimis» en Stripe`, 503, "sin_precio");
  cachedPrice = fits[0].id;
  return cachedPrice;
}

export async function createCheckoutSession(env, { siteUrl, origen, cif }) {
  const price = await resolvePrice(env);
  return stripe(env, "POST", "/checkout/sessions", {
    mode: "subscription",
    line_items: [{ price, quantity: 1 }],
    success_url: `${siteUrl}/asesorias/?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${siteUrl}/asesorias/?pago=cancelado`,
    locale: "es",
    billing_address_collection: "required",
    tax_id_collection: { enabled: "true" },
    metadata: { origen, plan: PLAN.codigo, ...(cif ? { cif } : {}) },
    subscription_data: { metadata: { origen, plan: PLAN.codigo } },
  });
}

const enc = (text) => new TextEncoder().encode(text);
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Verifica la cabecera Stripe-Signature (HMAC-SHA256 de "t.payload") con la tolerancia estándar de 5 minutos. */
export async function verifyWebhook(payload, header, secret, now = Date.now() / 1000, tolerance = 300) {
  if (!secret) throw new StripeError("Webhook no configurado", 503, "sin_secreto");
  const items = String(header || "")
    .split(",")
    .map((part) => part.split("="));
  const t = Number(items.find(([k]) => k === "t")?.[1]);
  const signatures = items.filter(([k]) => k === "v1").map(([, v]) => v || "");
  if (!t || !signatures.length) throw new StripeError("Firma ausente", 400, "firma");
  if (Math.abs(now - t) > tolerance) throw new StripeError("Firma fuera de plazo", 400, "firma");
  const key = await crypto.subtle.importKey("raw", enc(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const expected = hex(await crypto.subtle.sign("HMAC", key, enc(`${t}.${payload}`)));
  if (!signatures.some((s) => safeEqual(s, expected))) throw new StripeError("Firma no válida", 400, "firma");
  return JSON.parse(payload);
}
