"""Almacén SQLite (modo WAL) con esquema versionado por `PRAGMA user_version`.

Los datos públicos (convocatorias, concesiones de minimis) son una caché reconstruible
desde la BDNS. Cuentas, carteras y eventos de facturación son datos propios.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .bdns.models import Convocatoria
from .minimis import Award

_MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE convocatorias (
        codigo_bdns TEXT PRIMARY KEY,
        titulo TEXT NOT NULL,
        organo_nivel1 TEXT, organo_nivel2 TEXT, organo_nivel3 TEXT,
        fecha_recepcion TEXT, fecha_inicio TEXT, fecha_fin TEXT,
        presupuesto REAL, finalidad TEXT, es_minimis INTEGER NOT NULL DEFAULT 0,
        detalle_json TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    );
    CREATE INDEX ix_conv_recepcion ON convocatorias(fecha_recepcion);
    CREATE INDEX ix_conv_fin ON convocatorias(fecha_fin);
    CREATE TABLE convocatoria_region (codigo_bdns TEXT NOT NULL, nuts TEXT NOT NULL, nombre TEXT,
        PRIMARY KEY (codigo_bdns, nuts));
    CREATE TABLE convocatoria_sector (codigo_bdns TEXT NOT NULL, cnae TEXT NOT NULL,
        PRIMARY KEY (codigo_bdns, cnae));
    CREATE VIRTUAL TABLE convocatorias_fts USING fts5(codigo_bdns UNINDEXED, titulo, organo, finalidad);
    CREATE TABLE minimis_awards (
        award_id TEXT PRIMARY KEY, nif TEXT NOT NULL, beneficiario TEXT, fecha_concesion TEXT NOT NULL,
        importe_eur REAL NOT NULL, reglamento TEXT, concedente TEXT, codigo_bdns TEXT, sector_cnae TEXT,
        visto_en TEXT NOT NULL
    );
    CREATE INDEX ix_minimis_nif ON minimis_awards(nif, fecha_concesion);
    CREATE TABLE minimis_lookups (nif TEXT PRIMARY KEY, consultado_en TEXT NOT NULL, n_concesiones INTEGER NOT NULL);
    CREATE TABLE accounts (
        id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, plan TEXT NOT NULL,
        api_key_hash TEXT NOT NULL UNIQUE, stripe_customer TEXT, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE portfolio (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        nif TEXT NOT NULL, alias TEXT, PRIMARY KEY (account_id, nif)
    );
    CREATE TABLE processed_events (event_id TEXT PRIMARY KEY, processed_at TEXT NOT NULL);
    CREATE TABLE sync_runs (
        id INTEGER PRIMARY KEY, stream TEXT NOT NULL, desde TEXT, hasta TEXT,
        vistas INTEGER, nuevas INTEGER, errores INTEGER, terminado_en TEXT NOT NULL
    );
    """,
    # v2: validación lean (lista de espera y métricas agregadas sin datos personales)
    """
    CREATE TABLE leads (
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL,
        num_cifs_estimados INTEGER NOT NULL,
        cif_consultado TEXT,
        origen_clic TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        consentimiento TEXT NOT NULL
    );
    CREATE INDEX ix_leads_email ON leads(email);
    CREATE TABLE metrics_daily (
        day TEXT NOT NULL, event TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, event)
    );
    """,
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(_MIGRATIONS[version:], start=version + 1):
            with self.conn:
                self.conn.executescript(script)
                self.conn.execute(f"PRAGMA user_version = {i}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    # --- meta -----------------------------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    # --- convocatorias --------------------------------------------------------------------------
    def known_codigos(self, codigos: Iterable[str]) -> set[str]:
        codigos = list(codigos)
        found: set[str] = set()
        for i in range(0, len(codigos), 500):
            chunk = codigos[i : i + 500]
            marks = ",".join("?" * len(chunk))
            found |= {
                r[0]
                for r in self.conn.execute(
                    f"SELECT codigo_bdns FROM convocatorias WHERE codigo_bdns IN ({marks})", chunk
                )
            }
        return found

    def upsert_convocatoria(self, conv: Convocatoria, raw: dict) -> None:
        """Idempotente. Debe llamarse dentro de `transaction()` para agrupar escrituras."""
        c = self.conn
        organo = " · ".join(filter(None, (conv.organo_nivel2, conv.organo_nivel3)))
        c.execute(
            """INSERT INTO convocatorias (codigo_bdns, titulo, organo_nivel1, organo_nivel2, organo_nivel3,
                   fecha_recepcion, fecha_inicio, fecha_fin, presupuesto, finalidad, es_minimis, detalle_json,
                   actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(codigo_bdns) DO UPDATE SET titulo=excluded.titulo, organo_nivel1=excluded.organo_nivel1,
                   organo_nivel2=excluded.organo_nivel2, organo_nivel3=excluded.organo_nivel3,
                   fecha_recepcion=excluded.fecha_recepcion, fecha_inicio=excluded.fecha_inicio,
                   fecha_fin=excluded.fecha_fin, presupuesto=excluded.presupuesto, finalidad=excluded.finalidad,
                   es_minimis=excluded.es_minimis, detalle_json=excluded.detalle_json,
                   actualizado_en=excluded.actualizado_en""",
            (
                conv.codigo_bdns,
                conv.titulo,
                conv.organo_nivel1,
                conv.organo_nivel2,
                conv.organo_nivel3,
                _iso(conv.fecha_recepcion),
                _iso(conv.fecha_inicio_solicitud),
                _iso(conv.fecha_fin_solicitud),
                conv.presupuesto_total,
                conv.finalidad,
                int(conv.is_minimis),
                json.dumps(raw, ensure_ascii=False),
                _now(),
            ),
        )
        c.execute("DELETE FROM convocatoria_region WHERE codigo_bdns = ?", (conv.codigo_bdns,))
        c.executemany(
            "INSERT OR IGNORE INTO convocatoria_region VALUES (?, ?, ?)",
            [(conv.codigo_bdns, code, name) for code, name in conv.regiones if code],
        )
        c.execute("DELETE FROM convocatoria_sector WHERE codigo_bdns = ?", (conv.codigo_bdns,))
        c.executemany(
            "INSERT OR IGNORE INTO convocatoria_sector VALUES (?, ?)",
            [(conv.codigo_bdns, code) for code, _ in conv.sectores if code],
        )
        c.execute("DELETE FROM convocatorias_fts WHERE codigo_bdns = ?", (conv.codigo_bdns,))
        c.execute(
            "INSERT INTO convocatorias_fts VALUES (?, ?, ?, ?)",
            (conv.codigo_bdns, conv.titulo, organo, conv.finalidad or ""),
        )

    def iter_raw_convocatorias(self) -> Iterator[dict]:
        for row in self.conn.execute("SELECT detalle_json FROM convocatorias"):
            yield json.loads(row["detalle_json"])

    def codigos_received_since(self, since: date) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT codigo_bdns FROM convocatorias WHERE fecha_recepcion >= ?", (since.isoformat(),)
            )
        ]

    def convocatorias_for_site(self, today: date, window_days: int, limit: int) -> list[tuple[Convocatoria, str]]:
        """Abiertas primero (por cierre más próximo), después las más recientes de la ventana."""
        since = (today - timedelta(days=window_days)).isoformat()
        rows = self.conn.execute(
            """SELECT detalle_json, actualizado_en FROM convocatorias
               WHERE fecha_recepcion >= ? OR fecha_fin >= ?
               ORDER BY (fecha_fin IS NOT NULL AND fecha_fin >= ?) DESC,
                        CASE WHEN fecha_fin >= ? THEN fecha_fin END ASC,
                        fecha_recepcion DESC
               LIMIT ?""",
            (since, today.isoformat(), today.isoformat(), today.isoformat(), limit),
        )
        return [(Convocatoria.from_api(json.loads(r["detalle_json"])), r["actualizado_en"]) for r in rows]

    def open_convocatorias(self, today: date, limit: int = 5000) -> list[Convocatoria]:
        rows = self.conn.execute(
            """SELECT detalle_json FROM convocatorias
               WHERE (fecha_fin IS NULL OR fecha_fin >= ?) AND (fecha_inicio IS NULL OR fecha_inicio <= ?)
               ORDER BY fecha_recepcion DESC LIMIT ?""",
            (today.isoformat(), today.isoformat(), limit),
        )
        return [Convocatoria.from_api(json.loads(r["detalle_json"])) for r in rows]

    def search(self, text: str, limit: int = 20) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT codigo_bdns FROM convocatorias_fts WHERE convocatorias_fts MATCH ? LIMIT ?", (text, limit)
            )
        ]

    # --- minimis --------------------------------------------------------------------------------
    def upsert_awards(self, awards: Iterable[Award]) -> list[str]:
        """Inserta o actualiza concesiones; devuelve los `award_id` que no existían."""
        unique = {a.award_id: a for a in awards}
        stamp = _now()
        new: list[str] = []
        with self.conn:
            for a in unique.values():
                exists = self.conn.execute("SELECT 1 FROM minimis_awards WHERE award_id = ?", (a.award_id,)).fetchone()
                self.conn.execute(
                    """INSERT INTO minimis_awards (award_id, nif, beneficiario, fecha_concesion, importe_eur,
                           reglamento, concedente, codigo_bdns, sector_cnae, visto_en)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(award_id) DO UPDATE SET importe_eur=excluded.importe_eur,
                           reglamento=excluded.reglamento, fecha_concesion=excluded.fecha_concesion""",
                    (
                        a.award_id,
                        a.nif,
                        a.beneficiary,
                        a.granted_on.isoformat(),
                        a.amount_eur,
                        a.regulation,
                        a.grantor,
                        a.call_code,
                        a.sector_cnae,
                        stamp,
                    ),
                )
                if exists is None:
                    new.append(a.award_id)
        return new

    def awards_for(self, nifs: Iterable[str]) -> list[Award]:
        nifs = list(nifs)
        if not nifs:
            return []
        marks = ",".join("?" * len(nifs))
        rows = self.conn.execute(f"SELECT * FROM minimis_awards WHERE nif IN ({marks})", nifs)
        return [
            Award(
                award_id=r["award_id"],
                nif=r["nif"],
                beneficiary=r["beneficiario"] or "",
                granted_on=date.fromisoformat(r["fecha_concesion"]),
                amount_eur=r["importe_eur"],
                regulation=r["reglamento"] or "",
                grantor=r["concedente"] or "",
                call_code=r["codigo_bdns"],
                sector_cnae=r["sector_cnae"],
            )
            for r in rows
        ]

    def lookup_time(self, nif: str) -> str | None:
        """Instante (UTC, ISO 8601) de la última consulta real a la BDNS para ese CIF."""
        row = self.conn.execute("SELECT consultado_en FROM minimis_lookups WHERE nif = ?", (nif,)).fetchone()
        return row["consultado_en"] if row else None

    def lookup_is_fresh(self, nif: str, max_age: timedelta) -> bool:
        stamp = self.lookup_time(nif)
        return stamp is not None and datetime.now(UTC) - datetime.fromisoformat(stamp) < max_age

    def mark_lookup(self, nif: str, n_awards: int) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO minimis_lookups VALUES (?, ?, ?)
                   ON CONFLICT(nif) DO UPDATE SET consultado_en=excluded.consultado_en,
                       n_concesiones=excluded.n_concesiones""",
                (nif, _now(), n_awards),
            )

    # --- cuentas y carteras ---------------------------------------------------------------------
    def upsert_account(self, email: str, plan: str, api_key_hash: str, stripe_customer: str | None) -> tuple[int, bool]:
        """Crea la cuenta o reactiva/actualiza el plan si ya existe. Devuelve (id, creada)."""
        with self.conn:
            row = self.conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE accounts SET plan = ?, active = 1, stripe_customer = COALESCE(?, stripe_customer) "
                    "WHERE id = ?",
                    (plan, stripe_customer, row["id"]),
                )
                return row["id"], False
            cur = self.conn.execute(
                "INSERT INTO accounts (email, plan, api_key_hash, stripe_customer, created_at) VALUES (?, ?, ?, ?, ?)",
                (email, plan, api_key_hash, stripe_customer, _now()),
            )
            return int(cur.lastrowid), True

    def deactivate_customer(self, stripe_customer: str) -> int:
        with self.conn:
            return self.conn.execute(
                "UPDATE accounts SET active = 0 WHERE stripe_customer = ?", (stripe_customer,)
            ).rowcount

    def account_by_key_hash(self, key_hash: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM accounts WHERE api_key_hash = ? AND active = 1", (key_hash,)).fetchone()

    def portfolio(self, account_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute("SELECT nif, alias FROM portfolio WHERE account_id = ? ORDER BY nif", (account_id,))
        )

    def add_to_portfolio(self, account_id: int, items: Iterable[tuple[str, str | None]]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT INTO portfolio (account_id, nif, alias) VALUES (?, ?, ?) "
                "ON CONFLICT(account_id, nif) DO UPDATE SET alias = COALESCE(excluded.alias, alias)",
                [(account_id, nif, alias) for nif, alias in items],
            )

    def watchers(self, nifs: Iterable[str]) -> dict[str, list[str]]:
        """CIF -> emails de las cuentas activas que lo vigilan."""
        nifs = list(nifs)
        if not nifs:
            return {}
        marks = ",".join("?" * len(nifs))
        out: dict[str, list[str]] = {}
        for r in self.conn.execute(
            f"SELECT p.nif, a.email FROM portfolio p JOIN accounts a ON a.id = p.account_id "
            f"WHERE a.active = 1 AND p.nif IN ({marks})",
            nifs,
        ):
            out.setdefault(r["nif"], []).append(r["email"])
        return out

    def all_portfolio_nifs(self) -> set[str]:
        return {
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT p.nif FROM portfolio p JOIN accounts a ON a.id = p.account_id WHERE a.active = 1"
            )
        }

    def event_processed(self, event_id: str) -> bool:
        return (
            self.conn.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)).fetchone() is not None
        )

    def mark_event_processed(self, event_id: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO processed_events VALUES (?, ?)", (event_id, _now()))

    # --- operación ------------------------------------------------------------------------------
    def record_sync(
        self, stream: str, desde: date | None, hasta: date | None, vistas: int, nuevas: int, errores: int
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO sync_runs (stream, desde, hasta, vistas, nuevas, errores, terminado_en) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (stream, _iso(desde), _iso(hasta), vistas, nuevas, errores, _now()),
            )
        self.set_meta(f"last_sync_{stream}", _now())

    # --- validación lean -------------------------------------------------------------------------
    def add_lead(self, email: str, num_cifs: int, cif: str | None, origen: str, consentimiento: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO leads (email, num_cifs_estimados, cif_consultado, origen_clic, timestamp, consentimiento) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (email, num_cifs, cif, origen, _now(), consentimiento),
            )
            return int(cur.lastrowid)

    def leads(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT email, num_cifs_estimados, cif_consultado, origen_clic, timestamp FROM leads ORDER BY id"
        )
        return [dict(r) for r in rows]

    def delete_leads(self, email: str) -> int:
        """Derecho de supresión (RGPD): borra todos los envíos de ese email."""
        with self.conn:
            return self.conn.execute("DELETE FROM leads WHERE email = ?", (email.strip().lower(),)).rowcount

    def incr_metric(self, event: str, day: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO metrics_daily (day, event, count) VALUES (?, ?, 1) "
                "ON CONFLICT(day, event) DO UPDATE SET count = count + 1",
                (day, event),
            )

    def metrics(self, since_day: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT day, event, count FROM metrics_daily WHERE day >= ? ORDER BY day, event", (since_day,)
        )
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        q = lambda sql: self.conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "convocatorias": q("SELECT COUNT(*) FROM convocatorias"),
            "convocatorias_minimis": q("SELECT COUNT(*) FROM convocatorias WHERE es_minimis = 1"),
            "fecha_recepcion_max": q("SELECT MAX(fecha_recepcion) FROM convocatorias"),
            "fecha_recepcion_min": q("SELECT MIN(fecha_recepcion) FROM convocatorias"),
            "concesiones_minimis": q("SELECT COUNT(*) FROM minimis_awards"),
            "cifs_consultados": q("SELECT COUNT(*) FROM minimis_lookups"),
            "cuentas_activas": q("SELECT COUNT(*) FROM accounts WHERE active = 1"),
            "leads_validacion": q("SELECT COUNT(*) FROM leads"),
            "ultima_sync_convocatorias": self.get_meta("last_sync_convocatorias"),
        }


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
