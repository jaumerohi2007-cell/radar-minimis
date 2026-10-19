// Utilidades HTTP, configuración, cupos y métricas en D1 para las Pages Functions.
import * as K from "./constants.js";

export const json = (data, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

export function config(env = {}) {
  const billing = String(env.BILLING_MODE || "validation").trim().toLowerCase();
  return {
    // Modo desconocido = modo seguro: nunca se cobra por error.
    billingMode: billing === "stripe" ? "stripe" : "validation",
    freeLookupsPerDay: Number(env.FREE_LOOKUPS_PER_DAY || 10),
    freeGroupMax: Number(env.FREE_GROUP_MAX_CIFS || 2),
    fishCeiling: Number(env.TOPE_PESCA_EUR || K.RULES.pesca.tope),
    checkout: env.STRIPE_PAYMENT_LINK || "",
    userAgent: `RadarMinimis/${K.VERSION} (+${env.SITE_URL || "https://example.com"}; ${env.CONTACT_EMAIL || "contacto@example.com"})`,
    ipSalt: env.IP_SALT || "radar-minimis",
  };
}

export function proRequired(cfg, origen) {
  return cfg.billingMode === "validation"
    ? { codigo: "acceso_anticipado", origen, titulo: K.EARLY_ACCESS_TITLE, mensaje: K.EARLY_ACCESS_COPY }
    : { codigo: "requiere_plan", origen, checkout_url: cfg.checkout || null, mensaje: "Función del plan Asesorías Pro." };
}

/** El «día de la consulta» es el de España aunque el Worker corra en UTC. */
export const todayMadrid = (now = new Date()) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);

/** Identificador de cupo: SHA-256(sal|día|IP). No permite recuperar la IP y cambia cada día. */
export async function clientKey(request, salt, day, scope) {
  const ip = request.headers.get("CF-Connecting-IP") || "anon";
  const bytes = new TextEncoder().encode(`${salt}|${day}|${scope}|${ip}`);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...digest.slice(0, 16)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const SQL = {
  quota:
    "INSERT INTO quota (key, day, count) VALUES (?1, ?2, 1) ON CONFLICT(key) DO UPDATE SET " +
    "count = CASE WHEN quota.day = excluded.day THEN quota.count + 1 ELSE 1 END, day = excluded.day RETURNING count",
  quotaCleanup: "DELETE FROM quota WHERE day < ?1",
  metric:
    "INSERT INTO metrics_daily (day, event, count) VALUES (?1, ?2, 1) " +
    "ON CONFLICT(day, event) DO UPDATE SET count = metrics_daily.count + 1",
  lead:
    "INSERT INTO leads (email, num_cifs_estimados, cif_consultado, origen_clic, timestamp, consentimiento) " +
    "VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
};

/** Incrementa el cupo diario y devuelve el contador. Limpia filas antiguas de vez en cuando. */
export async function bumpQuota(db, key, day, random = Math.random) {
  const row = await db.prepare(SQL.quota).bind(key, day).first();
  if (random() < 0.01) await db.prepare(SQL.quotaCleanup).bind(day).run();
  return row ? Number(row.count) : 1;
}

export const incrMetric = (db, day, event) => db.prepare(SQL.metric).bind(day, event).run();

export const insertLead = (db, lead, timestamp) =>
  db
    .prepare(SQL.lead)
    .bind(lead.email, lead.num_cifs_estimados, lead.cif_consultado, lead.origen_clic, timestamp, K.CONSENTIMIENTO_VERSION)
    .run();
