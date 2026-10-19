# Radar Minimis · código del producto

Calculadora de **margen de minimis por CIF** («única empresa»), **informe imprimible para expediente** y **radar de subvenciones** sobre los datos abiertos de la BDNS. Se distribuye con miles de fichas pSEO de convocatorias y la pagarán las asesorías para vigilar a toda su cartera.

En la fase actual de **validación** (`BILLING_MODE=validation`) no se cobra nada: las funciones Pro muestran una lista de espera de acceso anticipado y se mide la demanda real.

La tesis y el plan están en [`../03_la_pepita_de_oro.md`](../03_la_pepita_de_oro.md). La verificación normativa está en [`../research/raw/07_verificacion_normativa.md`](../research/raw/07_verificacion_normativa.md).

```
src/
├── data_engine.py               ← CLI: sync, build-site, minimis, encaje, leads, cloudflare-constants, serve, daily…
├── radar_minimis/               ← motor de referencia (Python)
│   ├── minimis.py               NÚCLEO: topes verificados, ventana móvil fecha a fecha, «única empresa», SIEG, semáforo
│   ├── privacy.py               DNI/NIE/CIF con dígito de control; descarta personas físicas
│   ├── leads.py                 lista de espera (validación, honeypot, consentimiento), embudo, export, lectura de D1
│   ├── bdns/ · store.py · sync.py · matching.py · alerts.py · billing.py (Stripe, intacto tras BILLING_MODE)
│   ├── site/                    generador pSEO + calculadora + informe imprimible + panel demo /asesorias
│   ├── api/app.py               FastAPI (desarrollo local, Render/VPS)
│   └── cloudflare_export.py     genera cloudflare/constants.js: una sola fuente de verdad para topes y textos
├── cloudflare/                  ← motor JS para Workers (traducción 1:1 del de Python)
├── functions/api/               ← Cloudflare Pages Functions: minimis/[cif], waitlist, evento, health
├── d1/schema.sql                ← tablas leads, metrics_daily y quota (hash diario de IP, nunca la IP)
├── wrangler.toml                ← Pages + Functions + D1 (despliegue a 0 €/mes)
├── Dockerfile · render.yaml     ← alternativa portable (Render Free, Fly.io, VPS)
├── tests/                       ← pytest; incluye los vectores dorados compartidos y la suite de Node
│   ├── golden/minimis_vectors.json   9 casos calculados a mano que validan Python y JS por igual
│   └── js/                      node --test (sin dependencias npm)
└── deploy/vps/ · .github/workflows/sync_bdns.yml
```

## 1. Arranque local (Ubuntu / WSL)

```bash
cd src
curl -LsSf https://astral.sh/uv/install.sh | sh        # solo si no tienes uv
export UV_LINK_MODE=copy                                # recomendado si el proyecto está en /mnt/c (WSL)

uv sync                                                 # versiones exactas de uv.lock
uv run ruff check . && uv run pytest                    # Python + motor JS (Node ≥ 20) + paridad
uv run python data_engine.py sync --days 7 --max-details 1500   # datos reales de la BDNS (~12 min a 2 req/s)
RM_API_URL= uv run python data_engine.py build-site     # sitio pSEO en site_dist/
uv run python data_engine.py minimis <CIF> [<CIF vinculado>…]
RM_API_URL= uv run python data_engine.py serve          # http://127.0.0.1:8000: sitio + API + /api/docs
```

### Comandos del motor

| Comando | Qué hace |
|---|---|
| `sync [--days N \| --desde/--hasta] [--max-details N]` | Convocatorias nuevas y refresco de las recientes; reanudable |
| `build-site` | Fichas, hubs, `/minimis/`, `/minimis/informe/`, `/asesorias/`, sitemap, `_headers` con CSP (≤ 20.000 ficheros) |
| `minimis CIF [CIF…] [--fecha AAAA-MM-DD] [--json]` | Margen de la «única empresa» formada por esos CIF |
| `encaje CIF [--provincia ES417]` | Convocatorias abiertas que encajan con el CNAE inferido |
| `leads [--export leads_validacion.json] [--d1 radar-minimis-db] [--borrar EMAIL] [--dias 30]` | Métricas de validación (envíos, origen del clic, tamaño de cartera, embudo cálculo → modal → lead), exportación y supresión RGPD |
| `cloudflare-constants` | Regenera `cloudflare/constants.js` desde Python (un test falla si se olvida) |
| `sync-cartera` · `reindex` · `stats` · `serve` · `daily` | Igual que antes; `sync-cartera` no hace nada en modo validación |

## 2. Modo validación: la «puerta falsa» (`BILLING_MODE=validation`, por defecto)

El código de Stripe se mantiene intacto, pero solo se activa con `BILLING_MODE=stripe`: el webhook no se monta y el modo desconocido se trata como `validation`.

En modo validación, estas acciones abren el modal **«Acceso Asesorías Pro»**. La API responde `402` con el origen del clic:

| Acción del usuario | `origen_clic` |
|---|---|
| Grupo societario de más de `RM_FREE_GROUP_MAX_CIFS` CIF (por defecto 2; la interfaz ofrece 3 huecos de vinculados, el 2.º y el 3.º marcados «Pro») | `grupo_societario` |
| Vigilancia de cartera multi-CIF / «Importar mi propio CSV de CIFs» en `/asesorias/` | `cartera_lote` |
| Alertas semanales de subvenciones para la cartera | `alertas_cartera` |
| Informes de toda la cartera con logo, desde el informe imprimible | `informe_pdf` |

- **Qué se guarda:** `POST /api/waitlist` guarda `email`, `num_cifs_estimados`, `cif_consultado`, `origen_clic` y `timestamp` en SQLite (`leads`) o D1. Hay campo trampa contra bots, el consentimiento es obligatorio y el campo `cif_consultado` nunca almacena un DNI/NIE.
- **Embudo:** `POST /api/evento` cuenta por día y de forma agregada los modales abiertos y los informes generados e impresos, sin cookies.
- **Lectura:** `uv run python data_engine.py leads` (o `--d1 radar-minimis-db` en producción).

> Antes de publicar, rellena `RM_LEGAL_OWNER` y `RM_PRIVACY_EMAIL`: aparecen en el aviso legal y en la cláusula de consentimiento del modal.
> El copy promete «50 % de descuento vitalicio (19 €/mes)» sobre una tarifa de 38 €/mes. Si cambias la tarifa, actualiza el texto: el descuento debe referirse a un precio real.

## 3. Despliegue a **0,00 €/mes**: Cloudflare Pages + Pages Functions + D1 (recomendado)

Todo el producto de validación cabe en el plan Free de Cloudflare:
- 100.000 peticiones/día a Functions;
- D1 con 5 GB, 5 M lecturas/día y 100.000 escrituras/día;
- 20.000 ficheros por despliegue de Pages.

La API JavaScript (`functions/`) da exactamente el mismo resultado que la de Python: lo garantizan los vectores dorados y lo verifiqué contra la BDNS real con `wrangler pages dev`. Corre en el mismo origen que el sitio, así que no hay CORS ni arranques en frío.

```bash
cd src
npx --yes wrangler@4 login
npx --yes wrangler@4 d1 create radar-minimis-db                       # copia el database_id que imprime a wrangler.toml
npx --yes wrangler@4 d1 execute radar-minimis-db --remote --file d1/schema.sql
npx --yes wrangler@4 pages project create radar-minimis --production-branch main
openssl rand -hex 32 | npx --yes wrangler@4 pages secret put IP_SALT --project-name radar-minimis
# Edita [vars] en wrangler.toml: SITE_URL y CONTACT_EMAIL (BILLING_MODE ya es "validation").

export RM_SITE_URL=https://www.TU-DOMINIO RM_API_URL= RM_LEGAL_OWNER="Tu nombre o razón social, NIF" RM_PRIVACY_EMAIL=privacidad@TU-DOMINIO
uv run python data_engine.py sync --days 30 --max-details 4000     # carga inicial (≈35 min; reanudable)
uv run python data_engine.py build-site
npx --yes wrangler@4 pages deploy site_dist --project-name radar-minimis --branch main   # sitio + Functions + D1
curl -s https://radar-minimis.pages.dev/api/health                 # {"ok":true,…,"runtime":"cloudflare-pages-functions","d1":true}
```

**Automatización nocturna (GitHub Actions, también gratis):**

```bash
git init -b main && git add . && git commit -m "Radar Minimis v0.2" && gh repo create radar-minimis --private --source . --push
gh secret set CLOUDFLARE_API_TOKEN        # permisos «Cloudflare Pages: Edit» y «D1: Edit»
gh secret set CLOUDFLARE_ACCOUNT_ID
gh variable set CF_PAGES_PROJECT --body radar-minimis
gh variable set RM_SITE_URL --body https://www.TU-DOMINIO
gh variable set RM_CONTACT_EMAIL --body contacto@TU-DOMINIO
gh variable set RM_LEGAL_OWNER --body "Tu nombre o razón social, NIF"
gh variable set RM_PRIVACY_EMAIL --body privacidad@TU-DOMINIO
gh workflow run sync-bdns
```

Después:
- Asocia `www.TU-DOMINIO` en **Pages → Custom domains**.
- Verifica el dominio en **Google Search Console** y envía `/sitemap.xml`.
- Activa **Cloudflare Web Analytics**, que no usa cookies.

**Prueba local idéntica a producción** (lo que se usó para verificar esta versión):

```bash
npx --yes wrangler@4 d1 execute radar-minimis-db --local --file d1/schema.sql
npx --yes wrangler@4 pages dev site_dist --port 8788
uv run python data_engine.py leads --d1 radar-minimis-db              # en producción (usa --remote)
```

| Concepto | Coste |
|---|---|
| Cloudflare Pages + Functions + D1 + Web Analytics | 0 € |
| GitHub privado + Actions (~10 min/día) | 0 € |
| Dominio | ~11 €/año (el único gasto) |

### Alternativa: Render Free con Docker

`render.yaml` y `Dockerfile` sirven la API Python. Úsalos si prefieres Python en servidor.

Limitaciones del plan Free:
- **El servicio se duerme** tras 15 minutos sin tráfico, así que el primer cálculo tarda en despertar.
- **El disco es efímero.** La caché se reconstruye sola, pero la lista de espera no debe vivir ahí: deja `RM_LEADS_API_URL` vacío para que vaya a las Functions del sitio en Pages.

Pasos:
1. **New → Blueprint** en Render, apuntando al repositorio.
2. Define `RM_SITE_URL`, `RM_ALLOWED_ORIGINS` y `RM_CONTACT_EMAIL`.
3. Genera el sitio con `RM_API_URL=https://TU-SERVICIO.onrender.com`.

El `Dockerfile` también vale para Fly.io o un VPS.

## 4. Fase de pago (cuando el MRR cubra la cuota de autónomo)

1. Alta fiscal (ver §3 del plan).
2. Despliega la API Python con persistencia. Los pasos de VPS siguen en `deploy/vps/`: systemd, Caddy, `backup.sh`, timer diario.
3. Pon `BILLING_MODE=stripe`, `RM_STRIPE_WEBHOOK_SECRET` y `RM_STRIPE_PAYMENT_LINK`. La API no arranca en modo `stripe` sin el secreto del webhook.
4. El webhook `checkout.session.completed` crea la cuenta Pro (100 CIF; 1.900 céntimos = acceso anticipado) y envía la API key por Resend.
5. Exporta los leads (`leads --d1 radar-minimis-db --export leads_validacion.json`) y escríbeles por orden de solicitud.

## 5. Uso de la API

```bash
curl -s "https://TU-SITIO/api/minimis/<CIF>?vinculadas=<CIF2>&fecha=2026-11-30"   # fecha prevista de concesión
curl -s "https://TU-SITIO/api/minimis/<CIF>?fresco=1"                             # datos de la BDNS de < 10 min (informe)
curl -s -X POST https://TU-SITIO/api/waitlist -H 'Content-Type: application/json' \
  -d '{"email":"tu@asesoria.es","num_cifs_estimados":40,"origen_clic":"cartera_lote","consentimiento":true}'
```

Cada respuesta incluye:
- `consultas_bdns[].consultado_en` (fecha y hora real de la consulta a la BDNS);
- `ventana_desde` / `ventana_hasta`;
- los cuatro regímenes (general y SIEG siempre);
- `aviso_unica_empresa` y `semaforo`.

## 6. Cumplimiento (no negociable)

- **Atribución** en cada página, respuesta e informe: «Origen de los datos: Intervención General de la Administración del Estado», con la fecha de actualización.
- **Sin personas físicas.** DNI y NIE (también K/L/M) se rechazan en la API, se descartan en la ingesta y nunca se guardan en la lista de espera.
- **Sin aparentar carácter oficial.** El informe dice expresamente que no es un certificado. Por eso el modal promete «informes de minimis» y no «certificados».
- **Uso educado de la API de la BDNS.** Ritmo de 2 req/s, User-Agent con contacto y caché de 24 h (10 min con `fresco`).
- **RGPD en la lista de espera:**
  - consentimiento explícito con titular y finalidad;
  - borrado con `leads --borrar EMAIL`;
  - cupos con hash diario de IP, nunca la IP.

## 7. Calidad

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest     # 0 errores y 0 advertencias
```

## 8. Limitaciones conocidas (honestas)

- **SIEG:** el límite conjunto general + SIEG = 750.000 € es un **criterio prudente**. El art. 5.1 del Reg. 2023/2831 permite la acumulación sin fijar un tope conjunto expreso. Se indica en la interfaz.
- **Pesca:** 40.000 € (España, RD 1139/2024). Se aplica a convocatorias aprobadas desde su entrada en vigor; para el régimen base, `RM_TOPE_PESCA_EUR=30000`.
- **Límite de consultas de la API Python:** está en memoria (un proceso). En Cloudflare el cupo diario va en D1.
- **Docker:** el `Dockerfile` no se ha podido construir en este equipo, porque Docker Desktop no está integrado en WSL. Sí se verificó que existe la imagen base `ghcr.io/astral-sh/uv:0.13.0`.
- **Panel `/asesorias/`:** es una demo con 15 empresas ficticias (las convocatorias sí son reales). La cartera real está en la API Python (modo `stripe`).
- **Informe:** se genera en el navegador y se guarda como PDF con «Imprimir». No hay PDF de servidor.
