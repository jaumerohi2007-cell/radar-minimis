-- Esquema D1 (Cloudflare) para la fase de validación. Mismas tablas `leads` y `metrics_daily` que la
-- migración v2 de SQLite (radar_minimis/store.py); `quota` guarda solo hashes diarios de IP, nunca la IP.
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    num_cifs_estimados INTEGER NOT NULL,
    cif_consultado TEXT,
    origen_clic TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    consentimiento TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_leads_email ON leads(email);
CREATE TABLE IF NOT EXISTS metrics_daily (
    day TEXT NOT NULL, event TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, event)
);
CREATE TABLE IF NOT EXISTS quota (key TEXT PRIMARY KEY, day TEXT NOT NULL, count INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_quota_day ON quota(day);
