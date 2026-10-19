// POST /api/cuenta/cartera — añade o actualiza clientes {clientes: [{cif, alias, vinculadas}]} (máx. 100 CIF).
// DELETE /api/cuenta/cartera?cif=B12345674 — retira un cliente de la cartera.
import { CSQL, listPortfolio, requireAccount, upsertPortfolio } from "../../../cloudflare/cuentas.js";
import { normalize } from "../../../cloudflare/core.js";
import { json } from "../../../cloudflare/http.js";

export async function onRequestPost({ request, env }) {
  const { cuenta, response } = await requireAccount(request, env);
  if (response) return response;
  let payload;
  try {
    payload = await request.json();
  } catch (_) {
    return json({ detail: "Cuerpo JSON no válido." }, 422);
  }
  const clientes = payload?.clientes;
  if (!Array.isArray(clientes) || !clientes.length || clientes.length > 500)
    return json({ detail: "Envía entre 1 y 500 filas en «clientes»." }, 422);
  const result = await upsertPortfolio(env.DB, cuenta.id, clientes);
  return json({ ...result, cartera: await listPortfolio(env.DB, cuenta.id) });
}

export async function onRequestDelete({ request, env }) {
  const { cuenta, response } = await requireAccount(request, env);
  if (response) return response;
  const cif = normalize(new URL(request.url).searchParams.get("cif"));
  if (!cif) return json({ detail: "Falta el CIF." }, 422);
  await env.DB.prepare(CSQL.carteraDelete).bind(cuenta.id, cif).run();
  return json({ cartera: await listPortfolio(env.DB, cuenta.id) });
}
