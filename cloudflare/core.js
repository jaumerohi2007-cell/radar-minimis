// Motor de minimis para Cloudflare Pages Functions: traducción 1:1 de radar_minimis/privacy.py y minimis.py.
// Los textos y topes vienen de constants.js (generado desde Python) y tests/golden/minimis_vectors.json verifica
// que ambos motores dan exactamente el mismo resultado.
import * as K from "./constants.js";

const DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE";
const CIF_CONTROL_LETTERS = "JABCDEFGHI";
const CIF_RE = /^([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])$/;
const DNI_RE = /^(\d{8})([A-Z])$/;
const NIE_RE = /^([XYZ])(\d{7})([A-Z])$/;
const KLM_RE = /^([KLM])(\d{7})([A-Z])$/;
const LETTER_CONTROL = new Set("NPQRSW");
const DIGIT_CONTROL = new Set("ABEH");

export const LEGAL_ENTITY = "persona_juridica";
export const NATURAL_PERSON = "persona_fisica";
export const INVALID = "invalido";

export const normalize = (value) => String(value ?? "").replace(/[\s.\-/]/g, "").toUpperCase();

function cifControlIndex(digits) {
  let total = 0;
  for (let i = 0; i < digits.length; i += 1) {
    let n = Number(digits[i]);
    if (i % 2 === 0) {
      n *= 2; // posiciones impares (1.ª, 3.ª…): se duplican y se suman sus cifras
      n = Math.floor(n / 10) + (n % 10);
    }
    total += n;
  }
  return (10 - (total % 10)) % 10;
}

export function classifyNif(value) {
  const nif = normalize(value);
  let m = CIF_RE.exec(nif);
  if (m) {
    const [, letter, digits, control] = m;
    const idx = cifControlIndex(digits);
    const asDigit = String(idx);
    const asLetter = CIF_CONTROL_LETTERS[idx];
    let ok;
    if (LETTER_CONTROL.has(letter)) ok = control === asLetter;
    else if (DIGIT_CONTROL.has(letter)) ok = control === asDigit;
    else ok = control === asDigit || control === asLetter;
    return ok ? LEGAL_ENTITY : INVALID;
  }
  if ((m = DNI_RE.exec(nif))) return DNI_LETTERS[Number(m[1]) % 23] === m[2] ? NATURAL_PERSON : INVALID;
  if ((m = NIE_RE.exec(nif))) {
    const n = Number(String("XYZ".indexOf(m[1])) + m[2]);
    return DNI_LETTERS[n % 23] === m[3] ? NATURAL_PERSON : INVALID;
  }
  if ((m = KLM_RE.exec(nif))) return DNI_LETTERS[Number(m[2]) % 23] === m[3] ? NATURAL_PERSON : INVALID;
  return INVALID;
}

export function splitBeneficiary(text) {
  const clean = String(text ?? "").trim();
  const space = clean.indexOf(" ");
  const head = space === -1 ? clean : clean.slice(0, space);
  const rest = space === -1 ? "" : clean.slice(space + 1).trim();
  return classifyNif(head) !== INVALID ? [normalize(head), rest] : [null, clean];
}

export function classifyRegulation(text) {
  const t = String(text ?? "").toLowerCase();
  if (t.includes("1408/2013") || t.includes("agrícola") || t.includes("agricola")) return "agricola";
  if (t.includes("717/2014") || t.includes("pesca")) return "pesca";
  if (t.includes("2023/2832") || t.includes("360/2012") || t.includes("sieg") || t.includes("interés económico general"))
    return "sieg";
  if (t.includes("2023/2831") || t.includes("1407/2013") || t.includes("general")) return "general";
  return "desconocido";
}

// --- Fechas ISO (AAAA-MM-DD), siempre en UTC para evitar desfases horarios ----------------------------
const pad = (n) => String(n).padStart(2, "0");

export function threeYearsBefore(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return m === 2 && d === 29 ? `${y - 3}-02-28` : `${y - 3}-${pad(m)}-${pad(d)}`;
}

export function addDays(iso, days) {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function isIsoDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().startsWith(value);
}

export function windowStart(window, reference) {
  if (window === "ejercicio_en_curso_y_dos_anteriores") return `${Number(reference.slice(0, 4)) - 2}-01-01`;
  return addDays(threeYearsBefore(reference), 1);
}

export function semaforo(utilization) {
  if (utilization >= K.SEMAFORO_ROJO) return "rojo";
  if (utilization >= K.SEMAFORO_AMBAR) return "ambar";
  return "verde";
}

/** Fila de `minimis/busqueda` -> concesión; null si no es una persona jurídica válida. */
export function awardFromApi(row) {
  const [nif, name] = splitBeneficiary(row.beneficiario);
  if (!nif || classifyNif(nif) !== LEGAL_ENTITY) return null;
  const granted = String(row.fechaConcesion || "").slice(0, 10);
  if (!isIsoDate(granted) || row.ayudaEquivalente === null || row.ayudaEquivalente === undefined) return null;
  return {
    id: String(row.idConcesion ?? row.codigoConcesion),
    nif,
    beneficiary: name,
    granted_on: granted,
    amount: Number(row.ayudaEquivalente),
    regulation: String(row.reglamento || "").trim(),
    grantor: String(row.convocante || "").trim(),
    call_code: row.numeroConvocatoria ? String(row.numeroConvocatoria) : null,
  };
}

const round2 = (x) => Math.round(x * 100) / 100;
const sum = (list) => list.reduce((acc, a) => acc + a.amount, 0);
const COUNTS_AGAINST_GENERAL = new Set(["general", "agricola", "pesca", "desconocido"]);

/** Mismo contrato JSON que HeadroomReport.to_dict() en Python. */
export function computeHeadroom(awards, reference, nifs, { fishCeiling } = {}) {
  const group = [...new Set(nifs)];
  const unique = new Map();
  for (const a of awards) if (group.includes(a.nif) && a.granted_on <= reference && !unique.has(a.id)) unique.set(a.id, a);
  const all = [...unique.values()].sort((x, y) =>
    x.granted_on === y.granted_on ? (x.id < y.id ? 1 : -1) : x.granted_on < y.granted_on ? 1 : -1,
  );
  const rule = (r) => K.RULES[r];
  const rollingFrom = windowStart("tres_anos_moviles", reference);
  const fiscalFrom = windowStart("ejercicio_en_curso_y_dos_anteriores", reference);
  const rolling = all.filter((a) => a.granted_on >= rollingFrom);
  const byRegime = (r) => rolling.filter((a) => classifyRegulation(a.regulation) === r);
  const fiscalPesca = all.filter((a) => classifyRegulation(a.regulation) === "pesca" && a.granted_on >= fiscalFrom);

  const generalAwards = rolling.filter((a) => COUNTS_AGAINST_GENERAL.has(classifyRegulation(a.regulation)));
  const generalUsed = sum(generalAwards);
  const siegAwards = byRegime("sieg");
  const siegUsed = sum(siegAwards);
  const generalHeadroom = Math.max(0, Math.min(rule("general").tope - generalUsed, rule("sieg").tope - generalUsed - siegUsed));

  const usage = (r, used, headroom, pool, ceiling = rule(r).tope) => ({
    regimen: r,
    tope_eur: ceiling,
    usado_eur: round2(used),
    margen_eur: round2(headroom),
    ventana_desde: windowStart(rule(r).ventana, reference),
    ventana_hasta: reference,
    base_legal: rule(r).base,
    n_concesiones: pool.length,
    _used: used,
  });
  const usages = [
    usage("general", generalUsed, generalHeadroom, generalAwards),
    usage("sieg", siegUsed + generalUsed, Math.max(0, rule("sieg").tope - siegUsed - generalUsed), siegAwards),
  ];
  const agr = byRegime("agricola");
  if (agr.length) {
    const used = sum(agr);
    usages.push(usage("agricola", used, Math.max(0, Math.min(rule("agricola").tope - used, generalHeadroom)), agr));
  }
  if (fiscalPesca.length) {
    const ceiling = fishCeiling ?? rule("pesca").tope;
    const used = sum(fiscalPesca);
    usages.push(usage("pesca", used, Math.max(0, Math.min(ceiling - used, generalHeadroom)), fiscalPesca, ceiling));
  }
  const exceeded = usages.some((u) => u._used > u.tope_eur);
  const utilization = Math.max(...usages.map((u) => (u.tope_eur ? u._used / u.tope_eur : 0)));

  const warnings = [...K.BASE_WARNINGS];
  if (group.length === 1) warnings.unshift(K.WARN_SINGLE_CIF);
  if (exceeded) warnings.unshift(K.WARN_EXCEEDED);
  const unknown = byRegime("desconocido");
  if (unknown.length) warnings.push(K.WARN_UNKNOWN.replace("{n}", String(unknown.length)));
  if (rolling.some((a) => a.regulation.includes("1407/2013"))) warnings.push(K.WARN_LEGACY);
  if (fiscalPesca.length) warnings.push(K.WARN_PESCA);
  if (siegUsed) warnings.push(K.CRITERIO_ACUMULACION);

  const shownIds = new Set([...rolling, ...fiscalPesca].map((a) => a.id));
  const shown = all.filter((a) => shownIds.has(a.id));
  return {
    fecha_referencia: reference,
    ventana_desde: rollingFrom,
    ventana_hasta: reference,
    cifs: group,
    margen_general_eur: round2(generalHeadroom),
    tope_superado: exceeded,
    utilizacion: Math.round(utilization * 10000) / 10000,
    semaforo: semaforo(utilization),
    regimenes: usages.map(({ _used, ...u }) => u),
    concesiones: shown.map((a) => ({
      id: a.id,
      cif: a.nif,
      beneficiario: a.beneficiary,
      fecha_concesion: a.granted_on,
      importe_equivalente_eur: a.amount,
      reglamento: a.regulation,
      regimen: classifyRegulation(a.regulation),
      concedente: a.grantor,
      codigo_bdns: a.call_code,
    })),
    concesiones_fuera_de_ventana: all.length - shown.length,
    aviso_unica_empresa: K.SINGLE_UNDERTAKING_NOTICE,
    criterio_acumulacion: K.CRITERIO_ACUMULACION,
    advertencias: warnings,
  };
}
