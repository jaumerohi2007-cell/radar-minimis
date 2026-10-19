// GET /api/minimis/:cif — margen de minimis de la «única empresa». Mismo contrato JSON que la API Python.
import { BdnsError, minimisByNif } from "../../../cloudflare/bdns.js";
import { ATTRIBUTION, DISCLAIMER } from "../../../cloudflare/constants.js";
import { INVALID, NATURAL_PERSON, awardFromApi, classifyNif, computeHeadroom, isIsoDate, normalize } from "../../../cloudflare/core.js";
import { bumpQuota, clientKey, config, incrMetric, json, proRequired, todayMadrid } from "../../../cloudflare/http.js";

export async function onRequestGet({ request, params, env }) {
  const cfg = config(env);
  const url = new URL(request.url);
  const nifs = [];
  for (const value of [params.cif, ...(url.searchParams.get("vinculadas") || "").split(",")]) {
    if (!String(value ?? "").trim()) continue;
    const nif = normalize(value);
    const kind = classifyNif(nif);
    if (kind === NATURAL_PERSON)
      return json({ detail: `${nif} corresponde a una persona física: por protección de datos solo se admiten CIF de personas jurídicas.` }, 422);
    if (kind === INVALID) return json({ detail: `${nif || "(vacío)"} no es un CIF válido: revisa el dígito de control.` }, 422);
    if (!nifs.includes(nif)) nifs.push(nif);
  }
  if (!nifs.length) return json({ detail: "(vacío) no es un CIF válido: revisa el dígito de control." }, 422);
  if (nifs.length > cfg.freeGroupMax) return json({ detail: proRequired(cfg, "grupo_societario") }, 402);
  const fecha = url.searchParams.get("fecha");
  if (fecha && !isIsoDate(fecha)) return json({ detail: "Fecha no válida (AAAA-MM-DD)." }, 422);

  const today = todayMadrid();
  if (env.DB) {
    const count = await bumpQuota(env.DB, await clientKey(request, cfg.ipSalt, today, "minimis"), today);
    if (count > cfg.freeLookupsPerDay)
      return json({ detail: `Has alcanzado el límite gratuito de ${cfg.freeLookupsPerDay} consultas diarias. Con Asesorías Pro las consultas son ilimitadas.` }, 429);
  }
  const fresco = ["1", "true"].includes(url.searchParams.get("fresco") || "");
  let results;
  try {
    results = await Promise.all(nifs.map((nif) => minimisByNif(nif, { maxAgeSeconds: fresco ? 600 : 86400, userAgent: cfg.userAgent })));
  } catch (error) {
    if (!(error instanceof BdnsError) && !(error instanceof TypeError)) throw error;
    return json({ detail: "La BDNS no responde ahora mismo. Inténtalo en unos minutos." }, 503);
  }
  const awards = [];
  const consultas = [];
  const beneficiarios = {};
  results.forEach(({ rows, fetchedAt }, i) => {
    const own = rows.map(awardFromApi).filter((a) => a && a.nif === nifs[i]); // exige igualdad exacta de CIF
    awards.push(...own);
    consultas.push({ cif: nifs[i], consultado_en: fetchedAt, n_concesiones: own.length });
    for (const a of own) if (a.beneficiary) beneficiarios[a.nif] = a.beneficiary;
  });
  const report = computeHeadroom(awards, fecha || today, nifs, { fishCeiling: cfg.fishCeiling });
  if (env.DB) await incrMetric(env.DB, today, "calculo_minimis");
  return json({
    ...report,
    fecha_referencia_indicada: Boolean(fecha),
    consultas_bdns: consultas,
    beneficiarios,
    atribucion: ATTRIBUTION,
    aviso: DISCLAIMER,
    modo: cfg.billingMode,
  });
}
