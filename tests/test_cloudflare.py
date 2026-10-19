"""Despliegue a 0 €/mes: motor JS de Cloudflare, configuración y paridad con el motor Python."""

import re
import shutil
import sqlite3
import subprocess
import tomllib
from pathlib import Path

import pytest

from radar_minimis.cloudflare_export import TARGET, render_constants_js
from radar_minimis.store import Store

SRC = Path(__file__).resolve().parent.parent


def test_cloudflare_constants_are_generated_from_python():
    assert TARGET.read_text(encoding="utf-8") == render_constants_js(), (
        "cloudflare/constants.js está desfasado: ejecuta `uv run python data_engine.py cloudflare-constants`"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está instalado")
def test_node_suite_for_pages_functions():
    proc = subprocess.run(
        ["node", "--test", "tests/js/core.test.js", "tests/js/functions.test.js"],
        cwd=SRC,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert re.search(r"^# fail 0$", proc.stdout, re.M)


def _columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({table})")]


def test_d1_schema_matches_sqlite_migration():
    d1 = sqlite3.connect(":memory:")
    d1.executescript((SRC / "d1" / "schema.sql").read_text(encoding="utf-8"))
    store = Store(":memory:")
    for table in ("leads", "metrics_daily"):
        assert _columns(d1, table) == _columns(store.conn, table), table
    store.close()


def test_wrangler_render_and_docker_configs():
    wrangler = tomllib.loads((SRC / "wrangler.toml").read_text(encoding="utf-8"))
    assert wrangler["pages_build_output_dir"] == "site_dist"
    assert wrangler["vars"]["BILLING_MODE"] == "validation" and wrangler["vars"]["TOPE_PESCA_EUR"] == "40000"
    assert wrangler["d1_databases"][0]["binding"] == "DB"
    render = (SRC / "render.yaml").read_text(encoding="utf-8")
    assert "plan: free" in render and "healthCheckPath: /api/health" in render and "value: validation" in render
    docker = (SRC / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev" in docker and "USER app" in docker and "${PORT}" in docker
    for route in ("functions/api/minimis/[cif].js", "functions/api/waitlist.js", "functions/api/evento.js"):
        assert (SRC / route).is_file(), route
