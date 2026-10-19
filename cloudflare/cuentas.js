// Licencias del plan Asesorías Pro en D1: alta tras verificar el pago con la API de Stripe, clave de acceso
// (solo se guarda su SHA-256) y cartera de hasta PLAN.max_cifs CIF de personas jurídicas por cuenta.
import { PLAN } from "./constants.js";
import { LEGAL_ENTITY, NATURAL_PERSON, classifyNif, normalize } from "./core.js";
import { json } from "./http.js";
import { ACTIVE_STATUSES, stripe } from "./stripe.js";

const REISSUE_HOURS = 72; // la misma sesión de pago puede volver a emitir la clave durante 72 h
const VERIFY_HOURS = 12; // cada 12 h se comprueba en Stripe que la suscripción sigue activa
const SESSION_RE = /^cs_(live|test)_[A-Za-z0-9]{10,200}$/;
const KEY_RE = /^rm_[A-Za-z0-9_-]{32,64}$/;

export class CuentaError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const CSQL = {
  bySession: "SELECT * FROM cuentas WHERE checkout_session = ?1",
  byKey: "SELECT * FROM cuentas WHERE clave_hash = ?1",
  insert:
    "INSERT INTO cuentas (email, plan, clave_hash, stripe_customer, stripe_subscription, checkout_session, estado, activa, " +
    "creada_en, verificada_en, clave_emitida_en) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?9, ?9) RETURNING id",
  rotate: "UPDATE cuentas SET clave_hash = ?1, clave_emitida_en = ?2 WHERE id = ?3",
  estado: "UPDATE cuentas SET estado = ?1, activa = ?2, verificada_en = ?3 WHERE id = ?4",
  estadoPorSuscripcion: "UPDATE cuentas SET estado = ?1, activa = ?2, verificada_en = ?3 WHERE stripe_subscription = ?4",
  cartera:
    "SELECT cif, alias, vinculadas, alta_en, ultima_revision, ultimo_usado_eur, ultimo_margen_eur, ultima_utilizacion, " +
    "ultimo_semaforo, nuevas_ids FROM cartera WHERE cuenta_id = ?1 ORDER BY alias COLLATE NOCASE, cif",
  carteraCifs: "SELECT cif FROM cartera WHERE cuenta_id = ?1",
  carteraUpsert:
    "INSERT INTO cartera (cuenta_id, cif, alias, vinculadas, alta_en) VALUES (?1, ?2, ?3, ?4, ?5) " +
    "ON CONFLICT(cuenta_id, cif) DO UPDATE SET alias = excluded.alias, vinculadas = excluded.vinculadas",
  carteraDelete: "DELETE FROM cartera WHERE cuenta_id = ?1 AND cif = ?2",
  carteraIds: "SELECT ultimas_ids FROM cartera WHERE cuenta_id = ?1 AND cif = ?2",
  revision:
    "UPDATE cartera SET ultima_revision = ?3, ultimo_usado_eur = ?4, ultimo_margen_eur = ?5, ultima_utilizacion = ?6, " +
    "ultimo_semaforo = ?7, ultimas_ids = ?8, nuevas_ids = ?9 WHERE cuenta_id = ?1 AND cif = ?2",
};

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
export const sha256hex = async (text) => hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
const hoursSince = (iso, now) => (now.getTime() - Date.parse(iso)) / 3_600_000;

/** Clave de acceso: «rm_» + 32 bytes aleatorios en base64url (256 bits). */
export function newKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return `rm_${btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
}

export function bearer(request) {
  const m = /^Bearer\s+(\S+)$/i.exec(request.headers.get("Authorization") || "");
  return m && KEY_RE.test(m[1]) ? m[1] : null;
}

const publicAccount = (row) => ({
  email: row.email,
  plan: row.plan,
  estado: row.estado,
  activa: Boolean(row.activa),
  alta: row.creada_en,
  max_cifs: PLAN.max_cifs,
  max_vinculadas: PLAN.max_vinculadas,
  precio: PLAN.precio,
});

/**
 * Activa la licencia de una sesión de Checkout pagada y devuelve la clave en claro (única vez que existe).
 * Repetir la activación de la misma sesión en las primeras 72 h emite una clave nueva e invalida la anterior.
 */
export async function activate(env, sessionId, now = new Date()) {
  if (!SESSION_RE.test(String(sessionId || ""))) throw new CuentaError("Identificador de sesión de pago no válido.", 422);
  const session = await stripe(env, "GET", `/checkout/sessions/${sessionId}`, { expand: ["subscription"] });
  const paid = session.status === "complete" && ["paid", "no_payment_required"].includes(session.payment_status);
  if (session.mode !== "subscription" || !paid)
    throw new CuentaError("Stripe no confirma el pago de esta sesión. Si acabas de pagar, espera unos segundos y recarga.", 402);
  const sub = session.subscription;
  const subId = typeof sub === "string" ? sub : sub?.id || null;
  const status = (typeof sub === "object" && sub?.status) || "active";
  const customer = typeof session.customer === "string" ? session.customer : session.customer?.id || null;
  const email = String(session.customer_details?.email || session.customer_email || "").toLowerCase();
  const clave = newKey();
  const hash = await sha256hex(clave);
  const iso = now.toISOString();

  let row = await env.DB.prepare(CSQL.bySession).bind(sessionId).first();
  if (!row) {
    try {
      const active = ACTIVE_STATUSES.has(status) ? 1 : 0;
      const inserted = await env.DB.prepare(CSQL.insert)
        .bind(email, PLAN.codigo, hash, customer, subId, sessionId, status, active, iso)
        .first();
      return { clave, nueva: true, id: inserted.id, cuenta: publicAccount({ email, plan: PLAN.codigo, estado: status, activa: active, creada_en: iso }) };
    } catch (error) {
      row = await env.DB.prepare(CSQL.bySession).bind(sessionId).first(); // dos activaciones simultáneas
      if (!row) throw error;
    }
  }
  if (hoursSince(row.creada_en, now) > REISSUE_HOURS)
    throw new CuentaError("Esta sesión de pago ya se activó y el plazo de 72 h para volver a emitir la clave ha vencido.", 409);
  await env.DB.prepare(CSQL.rotate).bind(hash, iso, row.id).run();
  return { clave, nueva: false, id: row.id, cuenta: publicAccount(row) };
}

/** Cuenta de la clave Bearer (o null). Revalida en Stripe cada 12 h; si Stripe no responde, conserva el estado. */
export async function accountFrom(request, env, now = new Date()) {
  const token = bearer(request);
  if (!token || !env.DB) return null;
  const row = await env.DB.prepare(CSQL.byKey).bind(await sha256hex(token)).first();
  if (!row) return null;
  if (row.stripe_subscription && env.STRIPE_SECRET_KEY && hoursSince(row.verificada_en, now) > VERIFY_HOURS) {
    try {
      const sub = await stripe(env, "GET", `/subscriptions/${row.stripe_subscription}`);
      row.estado = sub.status;
      row.activa = ACTIVE_STATUSES.has(sub.status) ? 1 : 0;
      await env.DB.prepare(CSQL.estado).bind(row.estado, row.activa, now.toISOString(), row.id).run();
    } catch (_) {
      /* Stripe caído: no se bloquea a un cliente de pago por un fallo transitorio */
    }
  }
  return row;
}

/** Devuelve {cuenta} o {response} con 401 (sin clave válida) o 402 (suscripción no activa). */
export async function requireAccount(request, env) {
  const cuenta = await accountFrom(request, env);
  if (!cuenta) return { response: json({ detail: "Clave de acceso no válida o ausente." }, 401) };
  if (!cuenta.activa)
    return {
      response: json(
        { detail: { codigo: "suscripcion_inactiva", mensaje: `La suscripción consta como «${cuenta.estado}» en Stripe. Reactívala desde el portal de cliente.` } },
        402,
      ),
    };
  return { cuenta };
}

export const accountView = publicAccount;

function cleanCif(value) {
  const cif = normalize(value);
  const kind = classifyNif(cif);
  if (kind === LEGAL_ENTITY) return { cif };
  if (kind === NATURAL_PERSON) return { error: "persona física: no se admite (protección de datos)" };
  return { error: "CIF no válido (dígito de control)" };
}

/** Valida filas {cif, alias, vinculadas} (vinculadas: lista o texto separado por «|», «,», «;» o espacios). */
export function parseClients(items) {
  const validos = new Map();
  const rechazados = [];
  (Array.isArray(items) ? items : []).forEach((item, i) => {
    const fila = i + 1;
    const main = cleanCif(item?.cif);
    if (main.error) {
      rechazados.push({ fila, valor: String(item?.cif ?? "").slice(0, 20), motivo: main.error });
      return;
    }
    const raw = Array.isArray(item.vinculadas) ? item.vinculadas : String(item.vinculadas ?? "").split(/[|,;\s]+/);
    const linked = [];
    for (const value of raw) {
      if (!String(value ?? "").trim()) continue;
      const v = cleanCif(value);
      if (v.error) {
        rechazados.push({ fila, valor: String(value).slice(0, 20), motivo: `vinculada: ${v.error}` });
        return;
      }
      if (v.cif !== main.cif && !linked.includes(v.cif)) linked.push(v.cif);
    }
    if (linked.length > PLAN.max_vinculadas) {
      rechazados.push({ fila, valor: main.cif, motivo: `más de ${PLAN.max_vinculadas} empresas vinculadas` });
      return;
    }
    const alias = String(item.alias ?? "").replace(/\s+/g, " ").trim().slice(0, 120);
    validos.set(main.cif, { cif: main.cif, alias, vinculadas: linked });
  });
  return { validos: [...validos.values()], rechazados };
}

export async function listPortfolio(db, cuentaId) {
  const { results } = await db.prepare(CSQL.cartera).bind(cuentaId).all();
  return (results || []).map((r) => ({
    cif: r.cif,
    alias: r.alias,
    vinculadas: r.vinculadas ? r.vinculadas.split(",") : [],
    alta_en: r.alta_en,
    ultima_revision: r.ultima_revision,
    usado_eur: r.ultimo_usado_eur,
    margen_eur: r.ultimo_margen_eur,
    utilizacion: r.ultima_utilizacion,
    semaforo: r.ultimo_semaforo,
    concesiones_nuevas: r.nuevas_ids ? JSON.parse(r.nuevas_ids) : [],
  }));
}

/** Añade o actualiza clientes respetando el máximo del plan. Devuelve el resumen para la interfaz. */
export async function upsertPortfolio(db, cuentaId, items, now = new Date()) {
  const { validos, rechazados } = parseClients(items);
  const { results } = await db.prepare(CSQL.carteraCifs).bind(cuentaId).all();
  const existing = new Set((results || []).map((r) => r.cif));
  let total = existing.size;
  const statements = [];
  for (const c of validos) {
    if (!existing.has(c.cif)) {
      if (total >= PLAN.max_cifs) {
        rechazados.push({ fila: null, valor: c.cif, motivo: `cartera completa (${PLAN.max_cifs} CIF)` });
        continue;
      }
      total += 1;
    }
    statements.push(db.prepare(CSQL.carteraUpsert).bind(cuentaId, c.cif, c.alias, c.vinculadas.join(","), now.toISOString()));
  }
  if (statements.length) await db.batch(statements);
  return { guardados: statements.length, rechazados, total, max_cifs: PLAN.max_cifs };
}

/** Guarda la revisión de un CIF de la cartera y devuelve los id de concesión nuevos desde la revisión anterior. */
export async function recordReview(db, cuentaId, report, now = new Date()) {
  const cif = report.cifs[0];
  const row = await db.prepare(CSQL.carteraIds).bind(cuentaId, cif).first();
  if (!row) return null;
  const ids = report.concesiones.map((a) => a.id);
  const previous = row.ultimas_ids ? new Set(JSON.parse(row.ultimas_ids)) : null;
  const nuevas = previous ? ids.filter((id) => !previous.has(id)) : [];
  const general = report.regimenes.find((r) => r.regimen === "general");
  await db
    .prepare(CSQL.revision)
    .bind(cuentaId, cif, now.toISOString(), general.usado_eur, report.margen_general_eur, report.utilizacion, report.semaforo, JSON.stringify(ids), JSON.stringify(nuevas))
    .run();
  return { concesiones_nuevas: nuevas, primera_revision: previous === null };
}
