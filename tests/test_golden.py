"""Vectores dorados compartidos con el motor JavaScript de Cloudflare (tests/js/core.test.js)."""

import json
from datetime import date
from pathlib import Path

import pytest

from radar_minimis.minimis import Award, compute_headroom

CASES = json.loads((Path(__file__).parent / "golden" / "minimis_vectors.json").read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("case", CASES, ids=[c["nombre"] for c in CASES])
def test_golden_vector(case):
    awards = [
        Award(c["id"], c["cif"], "DEMO", date.fromisoformat(c["fecha"]), float(c["importe"]), c["reglamento"])
        for c in case["concesiones"]
    ]
    data = compute_headroom(
        awards, date.fromisoformat(case["referencia"]), case["cifs"], fish_ceiling_eur=case.get("tope_pesca")
    ).to_dict()
    expected = case["esperado"]
    for key in ("ventana_desde", "ventana_hasta", "margen_general_eur", "tope_superado"):
        if key in expected:
            assert data[key] == expected[key], key
    got = {r["regimen"]: r for r in data["regimenes"]}
    for regime, values in expected["regimenes"].items():
        for key, value in values.items():
            assert got[regime][key] == value, (regime, key)
