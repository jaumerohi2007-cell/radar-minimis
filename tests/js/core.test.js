import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { LEGAL_ENTITY, INVALID, NATURAL_PERSON, addDays, awardFromApi, classifyNif, computeHeadroom, splitBeneficiary, threeYearsBefore, windowStart } from "../../cloudflare/core.js";
import { validateLead, LeadError } from "../../cloudflare/leads.js";

const golden = JSON.parse(readFileSync(new URL("../golden/minimis_vectors.json", import.meta.url), "utf-8"));

for (const c of golden.casos) {
  test(`vector dorado: ${c.nombre}`, () => {
    const awards = c.concesiones.map((x) => ({ id: x.id, nif: x.cif, beneficiary: "DEMO", granted_on: x.fecha, amount: x.importe, regulation: x.reglamento, grantor: "", call_code: null }));
    const r = computeHeadroom(awards, c.referencia, c.cifs, { fishCeiling: c.tope_pesca });
    for (const key of ["ventana_desde", "ventana_hasta", "margen_general_eur", "tope_superado"]) {
      if (key in c.esperado) assert.equal(r[key], c.esperado[key], key);
    }
    const got = Object.fromEntries(r.regimenes.map((x) => [x.regimen, x]));
    for (const [regime, values] of Object.entries(c.esperado.regimenes)) {
      for (const [key, value] of Object.entries(values)) assert.equal(got[regime][key], value, `${regime}.${key}`);
    }
  });
}

test("clasificación de NIF igual que en Python", () => {
  for (const nif of ["B12345674", "A11111119", "B00000000", "Q2826000H", "b-1234567-4"]) assert.equal(classifyNif(nif), LEGAL_ENTITY, nif);
  for (const nif of ["12345678Z", "X1234567L", "K1234567L"]) assert.equal(classifyNif(nif), NATURAL_PERSON, nif);
  for (const nif of ["B12345675", "Q2826000A", "A1111111A", "12345678A", "", "HOLA"]) assert.equal(classifyNif(nif), INVALID, nif);
  assert.deepEqual(splitBeneficiary("B12345674 EMPRESA DEMO, SL"), ["B12345674", "EMPRESA DEMO, SL"]);
});

test("ventana móvil fecha a fecha con bisiestos", () => {
  assert.equal(windowStart("tres_anos_moviles", "2026-10-19"), "2023-10-20");
  assert.equal(windowStart("tres_anos_moviles", "2028-02-29"), "2025-03-01");
  assert.equal(windowStart("tres_anos_moviles", "2027-02-28"), "2024-02-29");
  assert.equal(windowStart("ejercicio_en_curso_y_dos_anteriores", "2026-10-19"), "2024-01-01");
  assert.equal(threeYearsBefore("2024-02-29"), "2021-02-28");
  assert.equal(addDays("2024-02-28", 1), "2024-02-29");
});

test("awardFromApi descarta personas físicas y exige datos completos", () => {
  const row = { idConcesion: 7, beneficiario: "B12345674 EMPRESA DEMO, SL", fechaConcesion: "2026-10-15", ayudaEquivalente: 19200, reglamento: "REG (UE) 2023/2831 de minimis, General", convocante: "DEMO", numeroConvocatoria: "892429" };
  assert.equal(awardFromApi(row).nif, "B12345674");
  assert.equal(awardFromApi({ ...row, beneficiario: "12345678Z PERSONA" }), null);
  assert.equal(awardFromApi({ ...row, ayudaEquivalente: null }), null);
});

test("validación de leads igual que en Python", () => {
  const base = { email: " Ana@Gestoria.ES ", num_cifs_estimados: "120", origen_clic: "cartera_lote", cif_consultado: "12345678Z", consentimiento: true };
  assert.deepEqual(validateLead(base), { email: "ana@gestoria.es", num_cifs_estimados: 120, cif_consultado: null, origen_clic: "cartera_lote" });
  assert.equal(validateLead({ web: "x" }), null);
  for (const bad of [{ email: "x" }, { num_cifs_estimados: "12.5" }, { num_cifs_estimados: 0 }, { origen_clic: "otro" }, { consentimiento: false }]) {
    assert.throws(() => validateLead({ ...base, ...bad }), LeadError);
  }
});
