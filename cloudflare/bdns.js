// Cliente BDNS para Workers: caché en la Cache API de Cloudflare (gratis, sin escrituras en D1).
export const BDNS_API = "https://www.infosubvenciones.es/bdnstrans/api";
const MAX_PAGES = 10;

export class BdnsError extends Error {}

/** Concesiones de minimis de un CIF. Devuelve {rows, fetchedAt} con la hora real de la consulta a la BDNS. */
export async function minimisByNif(nif, { maxAgeSeconds, userAgent, fetchImpl = fetch, cache = globalThis.caches?.default }) {
  const key = `${BDNS_API}/minimis/busqueda?vpd=GE&pageSize=500&nifCif=${encodeURIComponent(nif)}`;
  if (cache) {
    const hit = await cache.match(key);
    const fetchedAt = hit?.headers.get("x-rm-fetched-at");
    if (hit && fetchedAt && (Date.now() - Date.parse(fetchedAt)) / 1000 < maxAgeSeconds) {
      return { rows: (await hit.json()).content, fetchedAt };
    }
  }
  const rows = [];
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const resp = await fetchImpl(`${key}&page=${page}`, { headers: { Accept: "application/json", "User-Agent": userAgent } });
    if (!resp.ok) throw new BdnsError(`BDNS HTTP ${resp.status}`);
    const data = await resp.json();
    rows.push(...(data.content || []));
    if (data.last !== false || !(data.content || []).length) break;
  }
  const fetchedAt = new Date().toISOString();
  if (cache) {
    const body = JSON.stringify({ content: rows });
    const headers = { "Content-Type": "application/json", "Cache-Control": "max-age=86400", "x-rm-fetched-at": fetchedAt };
    await cache.put(key, new Response(body, { headers }));
  }
  return { rows, fetchedAt };
}
