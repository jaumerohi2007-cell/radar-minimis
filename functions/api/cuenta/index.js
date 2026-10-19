// GET /api/cuenta — datos de la licencia y cartera guardada (requiere «Authorization: Bearer <clave>»).
import { accountView, listPortfolio, requireAccount } from "../../../cloudflare/cuentas.js";
import { json } from "../../../cloudflare/http.js";

export async function onRequestGet({ request, env }) {
  const { cuenta, response } = await requireAccount(request, env);
  if (response) return response;
  return json({ cuenta: accountView(cuenta), cartera: await listPortfolio(env.DB, cuenta.id) });
}
