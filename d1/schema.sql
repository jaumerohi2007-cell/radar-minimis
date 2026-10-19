-- Esquema D1 (Cloudflare). Mismas tablas `leads` y `metrics_daily` que la
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

-- Plan Asesorías Pro (BILLING_MODE=stripe). La cuenta se crea solo tras verificar con la API de Stripe que la
-- sesión de Checkout está pagada; de la clave de acceso solo se guarda su SHA-256.
CREATE TABLE IF NOT EXISTS cuentas (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    plan TEXT NOT NULL,
    clave_hash TEXT NOT NULL UNIQUE,
    stripe_customer TEXT,
    stripe_subscription TEXT,
    checkout_session TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1,
    creada_en TEXT NOT NULL,
    verificada_en TEXT NOT NULL,
    clave_emitida_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cuentas_subscription ON cuentas(stripe_subscription);
-- Cartera: solo CIF de personas jurídicas. `ultimas_ids` guarda los id de concesión de la última revisión para
-- marcar como nuevas las que aparezcan en la siguiente.
CREATE TABLE IF NOT EXISTS cartera (
    cuenta_id INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
    cif TEXT NOT NULL,
    alias TEXT NOT NULL DEFAULT '',
    vinculadas TEXT NOT NULL DEFAULT '',
    alta_en TEXT NOT NULL,
    ultima_revision TEXT,
    ultimo_usado_eur REAL,
    ultimo_margen_eur REAL,
    ultima_utilizacion REAL,
    ultimo_semaforo TEXT,
    ultimas_ids TEXT,
    nuevas_ids TEXT,
    PRIMARY KEY (cuenta_id, cif)
);
