// GET /api/health
import { VERSION } from "../../cloudflare/constants.js";
import { config, json } from "../../cloudflare/http.js";

export function onRequestGet({ env }) {
  return json({ ok: true, version: VERSION, modo: config(env).billingMode, runtime: "cloudflare-pages-functions", d1: Boolean(env.DB) });
}
