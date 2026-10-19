"""Validación lean: lista de espera «Acceso Asesorías Pro», embudo de conversión y exportación.

Los envíos se guardan en SQLite (API Python) o en Cloudflare D1 (Pages Functions) con el mismo esquema, y las
métricas son contadores diarios agregados: no se guardan IP ni cookies.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import secrets
import statistics
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .privacy import NifKind, classify, normalize

ORIGENES = ("informe_pdf", "cartera_lote", "grupo_societario", "alertas_cartera")
EVENTOS_CLIENTE = ("informe_generado", "informe_impreso", "demo_asesorias_vista", *(f"modal_{o}" for o in ORIGENES))
CONSENTIMIENTO_VERSION = "lista-espera-v1-2026-10-19"
EXPORT_FIELDS = ("email", "num_cifs_estimados", "cif_consultado", "origen_clic", "timestamp")
MAX_NUM_CIFS = 100_000
_EMAIL_RE = re.compile(r"^[^@\s'\"<>]{1,64}@[^@\s'\"<>]+\.[^@\s'\"<>]{2,}$")

EARLY_ACCESS_TITLE = "Acceso Asesorías Pro"
EARLY_ACCESS_COPY = (
    "Monitoriza hasta 100 CIFs en automático y genera informes de minimis en 1 clic. Estamos activando cuentas por "
    "orden de solicitud con un 50% de descuento vitalicio (19 €/mes). Déjanos tu email profesional y el número "
    "aproximado de empresas que gestionas."
)


class LeadError(ValueError):
    """Error de validación con un mensaje apto para mostrar al usuario."""


@dataclass(frozen=True, slots=True)
class Lead:
    email: str
    num_cifs_estimados: int
    cif_consultado: str | None
    origen_clic: str


def valid_email(value: str) -> bool:
    return len(value) <= 254 and bool(_EMAIL_RE.match(value))


def validate_lead(payload: dict) -> Lead | None:
    """Devuelve None si el envío es de un bot (campo trampa relleno); lanza LeadError si no es válido."""
    if str(payload.get("web") or "").strip():
        return None
    email = str(payload.get("email") or "").strip().lower()
    if not valid_email(email):
        raise LeadError("Introduce un email profesional válido.")
    raw = payload.get("num_cifs_estimados")
    if isinstance(raw, bool) or not re.fullmatch(r"\d+", str(raw if raw is not None else "").strip()):
        raise LeadError("Indica cuántas empresas gestionas aproximadamente.")
    num = int(str(raw).strip())
    if not 1 <= num <= MAX_NUM_CIFS:
        raise LeadError(f"El número de empresas debe estar entre 1 y {MAX_NUM_CIFS}.")
    origen = payload.get("origen_clic")
    if origen not in ORIGENES:
        raise LeadError("Origen de la solicitud no válido.")
    if payload.get("consentimiento") is not True:
        raise LeadError("Necesitamos tu consentimiento para guardar el email.")
    cif = normalize(str(payload.get("cif_consultado") or ""))
    # Nunca se guarda un DNI/NIE: solo CIF de personas jurídicas válidos.
    return Lead(email, num, cif if cif and classify(cif) is NifKind.LEGAL_ENTITY else None, origen)


def size_bucket(n: int) -> str:
    for limit, label in ((10, "1-10"), (50, "11-50"), (100, "51-100"), (500, "101-500")):
        if n <= limit:
            return label
    return ">500"


def summarize(leads: list[dict], metrics: list[dict]) -> dict:
    sizes = [int(row["num_cifs_estimados"]) for row in leads]
    events: Counter[str] = Counter()
    for row in metrics:
        events[row["event"]] += int(row["count"])
    unique = len({row["email"] for row in leads})
    calculos = events["calculo_minimis"]
    modales = sum(events[f"modal_{o}"] for o in ORIGENES)
    return {
        "envios": len(leads),
        "emails_unicos": unique,
        "por_origen": dict(Counter(row["origen_clic"] for row in leads)),
        "tamano_cartera": dict(Counter(size_bucket(n) for n in sizes)),
        "mediana_cifs": statistics.median(sizes) if sizes else None,
        "cifs_declarados_total": sum(sizes),
        "eventos": dict(events),
        "conversion_calculo_a_lead": round(unique / calculos, 4) if calculos else None,
        "conversion_modal_a_lead": round(unique / modales, 4) if modales else None,
    }


def format_summary(summary: dict, *, source: str, days: int) -> str:
    pct = lambda v: "—" if v is None else f"{v * 100:.1f} %"  # noqa: E731
    lines = [
        f"Validación «Acceso Asesorías Pro» · fuente: {source} · métricas de los últimos {days} días",
        f"  Envíos: {summary['envios']}  ·  emails únicos: {summary['emails_unicos']}  ·  "
        f"CIF declarados en total: {summary['cifs_declarados_total']}  ·  mediana: {summary['mediana_cifs'] or '—'}",
        "  Por origen del clic: " + (", ".join(f"{k} {v}" for k, v in sorted(summary["por_origen"].items())) or "—"),
        "  Tamaño de cartera: " + (", ".join(f"{k}: {v}" for k, v in summary["tamano_cartera"].items()) or "—"),
        "  Embudo: cálculos {c} → modales abiertos {m} → leads únicos {l}".format(
            c=summary["eventos"].get("calculo_minimis", 0),
            m=sum(summary["eventos"].get(f"modal_{o}", 0) for o in ORIGENES),
            l=summary["emails_unicos"],
        ),
        f"  Conversión cálculo→lead: {pct(summary['conversion_calculo_a_lead'])}  ·  "
        f"modal→lead: {pct(summary['conversion_modal_a_lead'])}",
    ]
    return "\n".join(lines)


def export(leads: list[dict], path: Path) -> None:
    """Exporta a JSON (p. ej. leads_validacion.json) o CSV según la extensión."""
    rows = [{k: row.get(k) for k in EXPORT_FIELDS} for row in leads]
    if path.suffix.lower() == ".csv":
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=EXPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Cloudflare D1 (vía wrangler) -------------------------------------------------------------------
class D1Error(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess]


def d1_query(database: str, sql: str, *, runner: Runner = subprocess.run) -> list[dict]:
    """Ejecuta SQL en la base D1 remota con `wrangler d1 execute --json` (requiere `wrangler login`)."""
    cmd = ["npx", "--yes", "wrangler@4", "d1", "execute", database, "--remote", "--json", "--command", sql]
    proc = runner(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise D1Error((proc.stderr or proc.stdout or "wrangler falló").strip()[-600:])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise D1Error("wrangler no devolvió JSON") from exc
    # Una entrada por sentencia: [{"results": [...], "success": true, "meta": {...}}]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return list(data[0].get("results") or [])
    raise D1Error("respuesta de wrangler no reconocida")


def d1_leads(database: str, *, runner: Runner = subprocess.run) -> list[dict]:
    return d1_query(database, f"SELECT {', '.join(EXPORT_FIELDS)} FROM leads ORDER BY id", runner=runner)


def d1_metrics(database: str, since_day: str, *, runner: Runner = subprocess.run) -> list[dict]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since_day):
        raise ValueError("fecha no válida")
    return d1_query(database, f"SELECT day, event, count FROM metrics_daily WHERE day >= '{since_day}'", runner=runner)


def d1_delete_leads(database: str, email: str, *, runner: Runner = subprocess.run) -> None:
    email = email.strip().lower()
    if not valid_email(email):  # la expresión excluye comillas: no hay inyección posible en el literal
        raise ValueError("email no válido")
    d1_query(database, f"DELETE FROM leads WHERE email = '{email}'", runner=runner)


# --- Licencias del plan Asesorías Pro en D1 (las crea /api/stripe/activar) ------------------------------------
def d1_accounts(database: str, *, runner: Runner = subprocess.run) -> list[dict]:
    sql = (
        "SELECT c.id, c.email, c.plan, c.estado, c.activa, c.creada_en, c.verificada_en, "
        "(SELECT COUNT(*) FROM cartera p WHERE p.cuenta_id = c.id) AS cifs FROM cuentas c ORDER BY c.id"
    )
    return d1_query(database, sql, runner=runner)


def d1_rotate_key(database: str, account_id: int, *, runner: Runner = subprocess.run) -> str:
    """Emite una clave de acceso nueva (la anterior deja de valer) y la devuelve en claro una sola vez."""
    if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id < 1:
        raise ValueError("id de cuenta no válido")
    key = "rm_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode()).hexdigest()
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    # Literales generados aquí (hex, ISO, entero): no hay datos externos en la sentencia.
    sql = f"UPDATE cuentas SET clave_hash = '{digest}', clave_emitida_en = '{now}' WHERE id = {account_id} RETURNING id"
    if not d1_query(database, sql, runner=runner):
        raise ValueError(f"no existe la cuenta {account_id}")
    return key
