// Plan Asesorías Pro: Checkout, activación, licencias y cartera contra un D1 real (SQLite de Node con d1/schema.sql)
// y una API de Stripe simulada. Ninguna prueba usa claves reales.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, test } from "node:test";

import { LEGAL_ENTITY, classifyNif } from "../../cloudflare/core.js";
import { CSQL, parseClients, sha256hex } from "../../cloudflare/cuentas.js";
import { formEncode, resetPriceCache } from "../../cloudflare/stripe.js";
import { onRequestPost as checkout } from "../../functions/api/checkout.js";
import { onRequestPost as cartera, onRequestDelete as carteraDelete } from "../../functions/api/cuenta/cartera.js";
import { onRequestGet as cuenta } from "../../functions/api/cuenta/index.js";
import { onRequestGet as health } from "../../functions/api/health.js";
import { onRequestGet as minimis } from "../../functions/api/minimis/[cif].js";
import { onRequestPost as activar } from "../../functions/api/stripe/activar.js";
import { onRequestPost as webhook } from "../../functions/api/stripe/webhook.js";

const SCHEMA = readFileSync(new URL("../../d1/schema.sql", import.meta.url), "utf8");
const FAKE_KEY = "sk_test_ficticia_solo_para_tests";

/** Adaptador D1 sobre node:sqlite: misma interfaz (prepare/bind/first/run/all/batch) y parámetros ?N. */
class SqliteD1 {
  constructor() {
    this.db = new DatabaseSync(":memory:");
    this.db.exec(SCHEMA);
  }
  prepare(sql) {
    const make = (args) => ({
      bind: (...next) => make(next),
      first: async () => this.db.prepare(sql).get(...args) ?? null,
      run: async () => (this.db.prepare(sql).run(...args), { success: true }),
      all: async () => ({ results: this.db.prepare(sql).all(...args) }),
    });
    return make([]);
  }
  async batch(statements) {
    for (const s of statements) await s.run();
  }
}

/** Primer CIF válido (letra B) a partir de 7 dígitos: el dígito de control se busca por fuerza bruta. */
const cif = (n) => {
  const digits = String(n).padStart(7, "0");
  for (let d = 0; d < 10; d += 1) if (classifyNif(`B${digits}${d}`) === LEGAL_ENTITY) return `B${digits}${d}`;
  throw new Error("sin CIF");
};

const realFetch = globalThis.fetch;
let stripeCalls;
let sessions;
let subscriptions;
let bdnsRows;

beforeEach(() => {
  resetPriceCache();
  stripeCalls = [];
  sessions = {};
  subscriptions = {};
  bdnsRows = {};
  globalThis.fetch = async (url, init = {}) => {
    const u = new URL(url);
    if (u.hostname === "www.infosubvenciones.es") {
      const nif = u.searchParams.get("nifCif");
      return new Response(JSON.stringify({ content: bdnsRows[nif] || [], last: true }), { status: 200 });
    }
    assert.equal(u.hostname, "api.stripe.com");
    assert.equal(init.headers.Authorization, `Bearer ${FAKE_KEY}`);
    const method = init.method || "GET";
    stripeCalls.push({ method, path: u.pathname, query: u.searchParams, body: init.body ? new URLSearchParams(String(init.body)) : null });
    const ok = (data) => new Response(JSON.stringify(data), { status: 200 });
    if (method === "GET" && u.pathname === "/v1/prices")
      return ok({
        data: [
          { id: "price_otro", unit_amount: 1900, created: 3, recurring: { interval: "month" }, product: { name: "Otro producto", active: true } },
          { id: "price_anual", unit_amount: 19000, created: 2, recurring: { interval: "year" }, product: { name: "Radar Minimis — Plan Asesorías Pro", active: true } },
          { id: "price_rm", unit_amount: 1900, created: 1, recurring: { interval: "month", interval_count: 1 }, product: { name: "Radar Minimis — Plan Asesorías Pro", active: true } },
        ],
      });
    if (method === "POST" && u.pathname === "/v1/checkout/sessions") return ok({ id: "cs_test_nueva0000001", url: "https://checkout.stripe.com/c/pay/cs_test_nueva0000001" });
    if (method === "GET" && u.pathname.startsWith("/v1/checkout/sessions/")) {
      const s = sessions[u.pathname.split("/").pop()];
      return s ? ok(s) : new Response(JSON.stringify({ error: { message: "No such checkout.session", code: "resource_missing" } }), { status: 404 });
    }
    if (method === "GET" && u.pathname.startsWith("/v1/subscriptions/")) return ok(subscriptions[u.pathname.split("/").pop()]);
    if (method === "POST" && u.pathname === "/v1/billing_portal/sessions") return ok({ url: "https://billing.stripe.com/p/session/test_1" });
    throw new Error(`Stripe simulado: ruta no prevista ${method} ${u.pathname}`);
  };
});
afterEach(() => {
  globalThis.fetch = realFetch;
});

const stripeEnv = (extra = {}) => ({ DB: new SqliteD1(), BILLING_MODE: "stripe", STRIPE_SECRET_KEY: FAKE_KEY, SITE_URL: "https://radar.test", ...extra });
const req = (path, { key, ...init } = {}) =>
  new Request(`https://radar.test${path}`, {
    headers: { "CF-Connecting-IP": "203.0.113.9", "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) },
    ...init,
  });
const post = (path, body, key) => req(path, { method: "POST", body: JSON.stringify(body), key });

function paidSession(id, { paid = true, sub = "sub_1", status = "active" } = {}) {
  sessions[id] = {
    id,
    mode: "subscription",
    status: paid ? "complete" : "open",
    payment_status: paid ? "paid" : "unpaid",
    customer: "cus_1",
    customer_details: { email: "Despacho@Asesoria.test" },
    subscription: { id: sub, status },
  };
  subscriptions[sub] = { id: sub, status };
}

async function licensed(env) {
  paidSession("cs_test_pagada0000001");
  const resp = await activar({ request: post("/api/stripe/activar", { session_id: "cs_test_pagada0000001" }), env });
  assert.equal(resp.status, 201);
  return (await resp.json()).clave;
}

test("formEncode aplana objetos y listas al formato de Stripe", () => {
  const body = formEncode({ line_items: [{ price: "p", quantity: 1 }], expand: ["subscription"], meta: { a: "b" }, x: null });
  assert.equal(decodeURIComponent(body.toString()), "line_items[0][price]=p&line_items[0][quantity]=1&expand[0]=subscription&meta[a]=b");
});

test("POST /api/checkout crea una suscripción de 19,00 €/mes con el precio del producto Radar Minimis", async () => {
  const off = await checkout({ request: post("/api/checkout", { origen: "cartera_lote" }), env: { BILLING_MODE: "validation" } });
  assert.equal(off.status, 404);

  const env = stripeEnv();
  const resp = await checkout({ request: post("/api/checkout", { origen: "cartera_lote", cif: "B12345674" }), env });
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.ok(data.url.startsWith("https://checkout.stripe.com/"));
  assert.equal(data.precio, "19,00 €/mes");
  const created = stripeCalls.find((c) => c.path === "/v1/checkout/sessions").body;
  assert.equal(created.get("mode"), "subscription");
  assert.equal(created.get("line_items[0][price]"), "price_rm"); // ni el anual ni el de otro producto
  assert.equal(created.get("success_url"), "https://radar.test/asesorias/?session_id={CHECKOUT_SESSION_ID}");
  assert.equal(created.get("tax_id_collection[enabled]"), "true");
  assert.equal(created.get("metadata[cif]"), "B12345674");
  assert.equal(created.get("subscription_data[trial_period_days]"), "14");
  assert.equal(created.get("subscription_data[trial_settings][end_behavior][missing_payment_method]"), "cancel");

  stripeCalls = [];
  const fixed = await checkout({ request: post("/api/checkout", { origen: "informe_pdf" }), env: stripeEnv({ STRIPE_PRICE_ID: "price_fijo" }) });
  assert.equal(fixed.status, 200);
  assert.deepEqual(stripeCalls.map((c) => c.path), ["/v1/checkout/sessions"]);
  assert.equal(stripeCalls[0].body.get("line_items[0][price]"), "price_fijo");

  const nokey = await checkout({ request: post("/api/checkout", {}), env: stripeEnv({ STRIPE_SECRET_KEY: "" }) });
  assert.equal(nokey.status, 503);
  assert.ok(!JSON.stringify(await nokey.json()).includes("sk_"));
});

test("activación: solo con pago verificado; la clave se muestra una vez y D1 guarda su hash", async () => {
  const env = stripeEnv();
  paidSession("cs_test_impagada00001", { paid: false });
  const unpaid = await activar({ request: post("/api/stripe/activar", { session_id: "cs_test_impagada00001" }), env });
  assert.equal(unpaid.status, 402);
  const bogus = await activar({ request: post("/api/stripe/activar", { session_id: "cs_test_noexiste00001" }), env });
  assert.equal(bogus.status, 404);
  assert.equal((await activar({ request: post("/api/stripe/activar", { session_id: "x' OR 1=1" }), env })).status, 422);

  const clave = await licensed(env);
  assert.match(clave, /^rm_[A-Za-z0-9_-]{43}$/);
  const row = env.DB.db.prepare("SELECT * FROM cuentas").get();
  assert.equal(row.clave_hash, await sha256hex(clave));
  assert.ok(!JSON.stringify(row).includes(clave));
  assert.deepEqual([row.email, row.stripe_customer, row.stripe_subscription, row.activa], ["despacho@asesoria.test", "cus_1", "sub_1", 1]);

  // Repetir la activación (otro navegador) emite una clave nueva e invalida la anterior.
  const again = await activar({ request: post("/api/stripe/activar", { session_id: "cs_test_pagada0000001" }), env });
  assert.equal(again.status, 200);
  const nueva = (await again.json()).clave;
  assert.notEqual(nueva, clave);
  assert.equal((await cuenta({ request: req("/api/cuenta", { key: clave }), env })).status, 401);
  assert.equal((await cuenta({ request: req("/api/cuenta", { key: nueva }), env })).status, 200);
  env.DB.db.prepare("UPDATE cuentas SET creada_en = '2020-01-01T00:00:00.000Z'").run();
  assert.equal((await activar({ request: post("/api/stripe/activar", { session_id: "cs_test_pagada0000001" }), env })).status, 409);
});

test("activación durante la prueba gratuita (sin cargo todavía)", async () => {
  const env = stripeEnv();
  sessions.cs_test_prueba00000001 = {
    id: "cs_test_prueba00000001",
    mode: "subscription",
    status: "complete",
    payment_status: "no_payment_required",
    customer: "cus_2",
    customer_details: { email: "prueba@asesoria.test" },
    subscription: { id: "sub_2", status: "trialing" },
  };
  const resp = await activar({ request: post("/api/stripe/activar", { session_id: "cs_test_prueba00000001" }), env });
  assert.equal(resp.status, 201);
  const data = await resp.json();
  assert.deepEqual([data.cuenta.estado, data.cuenta.activa], ["trialing", true]);
});

test("cartera en D1: solo personas jurídicas, vinculadas y tope de 100 CIF", async () => {
  const env = stripeEnv();
  const clave = await licensed(env);
  assert.equal((await cartera({ request: post("/api/cuenta/cartera", { clientes: [{ cif: "B12345674" }] }), env })).status, 401);

  const resp = await cartera({
    request: post(
      "/api/cuenta/cartera",
      { clientes: [{ cif: "b-12345674", alias: "  Estudio   Norte ", vinculadas: "B12345682|B12345674" }, { cif: "12345678Z", alias: "Autónomo" }, { cif: "B12345675" }] },
      clave,
    ),
    env,
  });
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.equal(data.guardados, 1);
  assert.deepEqual(data.cartera.map((c) => [c.cif, c.alias, c.vinculadas]), [["B12345674", "Estudio Norte", ["B12345682"]]]);
  assert.deepEqual(data.rechazados.map((r) => r.motivo), ["persona física: no se admite (protección de datos)", "CIF no válido (dígito de control)"]);

  const many = Array.from({ length: 120 }, (_, i) => ({ cif: cif(2000000 + i) }));
  const full = await (await cartera({ request: post("/api/cuenta/cartera", { clientes: many }, clave), env })).json();
  assert.equal(full.total, 100);
  assert.equal(full.rechazados.filter((r) => r.motivo.startsWith("cartera completa")).length, 21);

  const del = await carteraDelete({ request: req("/api/cuenta/cartera?cif=B12345674", { method: "DELETE", key: clave }), env });
  assert.equal((await del.json()).cartera.length, 99);
  assert.equal(parseClients([{ cif: "B12345674", vinculadas: [cif(1), cif(2), cif(3), cif(4)] }]).rechazados[0].motivo, "más de 3 empresas vinculadas");
});

const award = (id, nif, fecha, importe) => ({ idConcesion: id, beneficiario: `${nif} CLIENTE DEMO, SL`, fechaConcesion: fecha, ayudaEquivalente: importe, reglamento: "REG (UE) 2023/2831 de minimis, General", convocante: "DEMO", numeroConvocatoria: "1" });

test("licencia activa: sin cupo, grupos de 4 CIF y concesiones nuevas desde la revisión anterior", async () => {
  const env = stripeEnv({ FREE_LOOKUPS_PER_DAY: "1" });
  const clave = await licensed(env);
  await cartera({ request: post("/api/cuenta/cartera", { clientes: [{ cif: "B12345674", alias: "Cliente" }] }, clave), env });
  bdnsRows.B12345674 = [award(1, "B12345674", "2025-01-10", 1000)];
  const group = `/api/minimis/B12345674?vinculadas=${[cif(11), cif(12), cif(13)].join(",")}`;
  const first = await minimis({ request: req(group, { key: clave }), params: { cif: "B12345674" }, env });
  assert.equal(first.status, 200);
  const r1 = await first.json();
  assert.equal(r1.plan, "pro_100");
  assert.deepEqual(r1.revision, { concesiones_nuevas: [], primera_revision: true });

  bdnsRows.B12345674.push(award(2, "B12345674", "2026-01-10", 2000));
  const second = await (await minimis({ request: req("/api/minimis/B12345674", { key: clave }), params: { cif: "B12345674" }, env })).json();
  assert.deepEqual(second.revision, { concesiones_nuevas: ["2"], primera_revision: false });
  const stored = (await (await cuenta({ request: req("/api/cuenta", { key: clave }), env })).json()).cartera[0];
  assert.deepEqual([stored.usado_eur, stored.concesiones_nuevas, stored.semaforo], [3000, ["2"], "verde"]);

  const tooBig = await minimis({ request: req(`${group},${cif(14)}`, { key: clave }), params: { cif: "B12345674" }, env });
  assert.equal(tooBig.status, 422);
  // Sin clave: el grupo vuelve a ser de pago y el cupo gratuito (1/día) se aplica.
  assert.equal((await minimis({ request: req(group), params: { cif: "B12345674" }, env })).status, 402);
});

test("la licencia se revalida contra Stripe y el webhook firmado aplica la baja", async () => {
  const env = stripeEnv({ STRIPE_WEBHOOK_SECRET: "whsec_ficticio" });
  const clave = await licensed(env);
  subscriptions.sub_1 = { id: "sub_1", status: "canceled" };
  env.DB.db.prepare("UPDATE cuentas SET verificada_en = '2020-01-01T00:00:00.000Z'").run();
  const resp = await cuenta({ request: req("/api/cuenta", { key: clave }), env });
  assert.equal(resp.status, 402);
  assert.equal((await resp.json()).detail.codigo, "suscripcion_inactiva");

  env.DB.db.prepare("UPDATE cuentas SET activa = 1, estado = 'active', verificada_en = ?1").run(new Date().toISOString());
  const payload = JSON.stringify({ type: "customer.subscription.deleted", data: { object: { id: "sub_1", status: "canceled" } } });
  const t = Math.floor(Date.now() / 1000);
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode("whsec_ficticio"), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = [...new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${t}.${payload}`)))].map((b) => b.toString(16).padStart(2, "0")).join("");
  const bad = await webhook({ request: req("/api/stripe/webhook", { method: "POST", body: payload, headers: { "Stripe-Signature": `t=${t},v1=00` } }), env });
  assert.equal(bad.status, 400);
  const good = await webhook({ request: req("/api/stripe/webhook", { method: "POST", body: payload, headers: { "Stripe-Signature": `t=${t},v1=${sig}` } }), env });
  assert.equal(good.status, 200);
  assert.equal(env.DB.db.prepare(CSQL.byKey).get(await sha256hex(clave)).activa, 0);
  assert.equal((await webhook({ request: req("/api/stripe/webhook", { method: "POST", body: payload }), env: stripeEnv() })).status, 503);
});

test("GET /api/health?stripe=1 informa del precio y del tipo de clave sin exponerla", async () => {
  const data = await (await health({ request: req("/api/health?stripe=1"), env: stripeEnv() })).json();
  assert.deepEqual([data.modo, data.stripe.clave, data.stripe.price_id, data.stripe.price_fijado], ["stripe", "test", "price_rm", false]);
  assert.ok(!JSON.stringify(data).includes(FAKE_KEY));
});
