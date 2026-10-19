"""Genera `cloudflare/constants.js`: una sola fuente de verdad (Python) para topes, textos legales y avisos.

El motor JavaScript de Pages Functions importa ese fichero; `tests/test_cloudflare.py` falla si queda desfasado.
Regenerar con: `uv run python data_engine.py cloudflare-constants`.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import ATTRIBUTION, DISCLAIMER, __version__
from . import leads as L
from . import minimis as M

TARGET = Path(__file__).resolve().parent.parent / "cloudflare" / "constants.js"


def render_constants_js() -> str:
    values = {
        "VERSION": __version__,
        "ATTRIBUTION": ATTRIBUTION,
        "DISCLAIMER": DISCLAIMER,
        "SINGLE_UNDERTAKING_NOTICE": M.SINGLE_UNDERTAKING_NOTICE,
        "CRITERIO_ACUMULACION": M.CRITERIO_ACUMULACION,
        "BASE_WARNINGS": list(M.BASE_WARNINGS),
        "WARN_SINGLE_CIF": M.WARN_SINGLE_CIF,
        "WARN_EXCEEDED": M.WARN_EXCEEDED,
        "WARN_UNKNOWN": M.WARN_UNKNOWN,
        "WARN_LEGACY": M.WARN_LEGACY,
        "WARN_PESCA": M.WARN_PESCA,
        "SEMAFORO_AMBAR": M.SEMAFORO_AMBAR,
        "SEMAFORO_ROJO": M.SEMAFORO_ROJO,
        "PESCA_BASE_CEILING_EUR": M.PESCA_BASE_CEILING_EUR,
        "RULES": {
            r.value: {"tope": rule.ceiling_eur, "ventana": rule.window.value, "base": rule.legal_basis}
            for r, rule in M.RULES.items()
        },
        "ORIGENES": list(L.ORIGENES),
        "EVENTOS_CLIENTE": list(L.EVENTOS_CLIENTE),
        "CONSENTIMIENTO_VERSION": L.CONSENTIMIENTO_VERSION,
        "EARLY_ACCESS_TITLE": L.EARLY_ACCESS_TITLE,
        "EARLY_ACCESS_COPY": L.EARLY_ACCESS_COPY,
        "MAX_NUM_CIFS": L.MAX_NUM_CIFS,
    }
    lines = [
        "// GENERADO por `uv run python data_engine.py cloudflare-constants` desde radar_minimis (Python).",
        "// No editar a mano: tests/test_cloudflare.py comprueba que coincide con el motor Python.",
    ]
    lines += [f"export const {name} = {json.dumps(value, ensure_ascii=False)};" for name, value in values.items()]
    return "\n".join(lines) + "\n"


def write_constants(target: Path = TARGET) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_constants_js(), encoding="utf-8")
    return target
