import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { onRequestPost as evento } from "../../functions/api/evento.js";
import { onRequestGet as health } from "../../functions/api/health.js";
import { onRequestGet as minimis } from "../../functions/api/minimis/[cif].js";
import { onRequestPost as waitlist } from "../../functions/api/waitlist.js";
import { SQL } from "../../cloudflare/http.js";

/** D1 mínimo en memoria que entiende las sentencias de cloudflare/http.js. */
class FakeD1 {
  constructor() {
    this.quota = new Map();
    this.metrics = new Map();
    this.leads = [];
  }
  prepare(sql) {
    const db = this;
    return {
      bind: (...args) => ({
        async first() {
          assert.equal(sql, SQL.quota);
          const [key, day] = args;
          const prev = db.quota.get(key);
          const count = prev && prev.day === day ? prev.count + 1 : 1;
          db.quota.set(key, { day, count });
          return { count };
        },
        async run() {
          if (sql === SQL.metric) db.metrics.set(args.join("|"), (db.metrics.get(args.join("|")) || 0) + 1);
          else if (sql === SQL.lead) db.leads.push(args);
          else if (sql !== SQL.quotaCleanup) throw new Error(`SQL inesperado: ${sql}`);
          return { success: true };
        },
      }),
    };
  }
}

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

function bdnsStub(rowsByNif) {
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    const nif = new URL(url).searchParams.get("nifCif");
    return new Response(JSON.stringify({ content: rowsByNif[nif] || [], last: true }), { status: 200 });
  };
  return calls;
}

const row = (id, nif, fecha, importe) => ({ idConcesion: id, beneficiario: `${nif} EMPRESA DEMO, SL`, fechaConcesion: fecha, ayudaEquivalente: importe, reglamento: "REG (UE) 2023/2831 de minimis, General", convocante: "AUTONOMICA DEMO", numeroConvocatoria: "892429" });
const req = (path, init) => new Request(`https://radar.test${path}`, { headers: { "CF-Connecting-IP": "203.0.113.7", "Content-Type": "application/json" }, ...init });

test("GET /api/minimis calcula el margen con la hora real de la consulta a la BDNS", async () => {
  bdnsStub({ B12345674: [row(1, "B12345674", "2025-05-01", 100000), row(2, "B12345682", "2025-05-01", 5000)] });
  const env = { DB: new FakeD1() };
  const resp = await minimis({ request: req("/api/minimis/B12345674"), params: { cif: "B12345674" }, env });
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.equal(data.margen_general_eur, 200000); // la coincidencia parcial B12345682 (CIF válido) se descarta
  assert.ok(Date.parse(data.consultas_bdns[0].consultado_en));
  assert.equal(data.modo, "validation");
  assert.ok(data.aviso_unica_empresa.includes("art. 2.2"));
  assert.equal(env.DB.metrics.size, 1);
});

test("GET /api/minimis: privacidad, grupo grande y cupo diario", async () => {
  bdnsStub({});
  const env = { DB: new FakeD1(), FREE_LOOKUPS_PER_DAY: "1" };
  const dni = await minimis({ request: req("/api/minimis/12345678Z"), params: { cif: "12345678Z" }, env });
  assert.equal(dni.status, 422);
  const group = await minimis({ request: req("/api/minimis/B12345674?vinculadas=A11111119,B00000000"), params: { cif: "B12345674" }, env });
  assert.equal(group.status, 402);
  assert.equal((await group.json()).detail.origen, "grupo_societario");
  const first = await minimis({ request: req("/api/minimis/B12345674"), params: { cif: "B12345674" }, env });
  const second = await minimis({ request: req("/api/minimis/B12345674"), params: { cif: "B12345674" }, env });
  assert.deepEqual([first.status, second.status], [200, 429]);
  assert.ok([...env.DB.quota.keys()].every((k) => !k.includes("203.0.113.7"))); // nunca se guarda la IP
});

test("POST /api/waitlist guarda leads válidos en D1 y protege la privacidad", async () => {
  const env = { DB: new FakeD1() };
  const post = (body) => waitlist({ request: req("/api/waitlist", { method: "POST", body: JSON.stringify(body) }), env });
  const ok = await post({ email: "Gestor@Asesoria.test", num_cifs_estimados: 40, origen_clic: "grupo_societario", cif_consultado: "12345678Z", consentimiento: true });
  assert.equal(ok.status, 201);
  assert.deepEqual(env.DB.leads[0].slice(0, 4), ["gestor@asesoria.test", 40, null, "grupo_societario"]);
  assert.equal((await post({ email: "bot@x.es", web: "spam" })).status, 201);
  assert.equal(env.DB.leads.length, 1);
  const bad = await post({ email: "x", num_cifs_estimados: 1, origen_clic: "cartera_lote", consentimiento: true });
  assert.equal(bad.status, 422);
});

test("POST /api/evento solo acepta eventos de la lista blanca", async () => {
  const env = { DB: new FakeD1() };
  const post = (tipo) => evento({ request: req("/api/evento", { method: "POST", body: JSON.stringify({ tipo }) }), env });
  assert.equal((await post("modal_cartera_lote")).status, 204);
  assert.equal((await post("drop table")).status, 422);
  assert.equal([...env.DB.metrics.keys()][0].endsWith("|modal_cartera_lote"), true);
});

test("GET /api/health y modo desconocido = modo seguro", async () => {
  const data = await (await health({ env: { BILLING_MODE: "cobrar-ya" } })).json();
  assert.equal(data.modo, "validation");
  assert.equal(data.runtime, "cloudflare-pages-functions");
});
