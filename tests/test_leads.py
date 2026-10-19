import json
import subprocess

import pytest
from conftest import CIF_A

import data_engine
from radar_minimis import leads
from radar_minimis.store import Store


def test_validate_lead_normalizes_and_protects_privacy():
    lead = leads.validate_lead(
        {
            "email": " Ana@Gestoria.ES ",
            "num_cifs_estimados": "120",
            "origen_clic": "cartera_lote",
            "cif_consultado": "12345678Z",
            "consentimiento": True,
        }
    )
    assert lead == leads.Lead("ana@gestoria.es", 120, None, "cartera_lote")
    assert leads.validate_lead({"web": "x"}) is None  # campo trampa: bot
    with pytest.raises(leads.LeadError):
        leads.validate_lead({"email": "a@b.es", "num_cifs_estimados": 1, "origen_clic": "x", "consentimiento": True})


def test_summary_funnel_and_export(tmp_path):
    rows = [
        {
            "email": "a@x.es",
            "num_cifs_estimados": 8,
            "cif_consultado": CIF_A,
            "origen_clic": "grupo_societario",
            "timestamp": "2026-10-19T10:00:00+00:00",
        },
        {
            "email": "a@x.es",
            "num_cifs_estimados": 8,
            "cif_consultado": None,
            "origen_clic": "informe_pdf",
            "timestamp": "2026-10-19T11:00:00+00:00",
        },
        {
            "email": "b@y.es",
            "num_cifs_estimados": 140,
            "cif_consultado": None,
            "origen_clic": "cartera_lote",
            "timestamp": "2026-10-19T12:00:00+00:00",
        },
    ]
    metrics = [
        {"day": "2026-10-19", "event": "calculo_minimis", "count": 40},
        {"day": "2026-10-19", "event": "modal_cartera_lote", "count": 5},
    ]
    summary = leads.summarize(rows, metrics)
    assert (summary["envios"], summary["emails_unicos"], summary["cifs_declarados_total"]) == (3, 2, 156)
    assert summary["tamano_cartera"] == {"1-10": 2, "101-500": 1}
    assert summary["conversion_calculo_a_lead"] == 0.05 and summary["conversion_modal_a_lead"] == 0.4
    assert "Conversión cálculo→lead: 5.0 %" in leads.format_summary(summary, source="test", days=30)
    out = tmp_path / "leads_validacion.json"
    leads.export(rows, out)
    assert json.loads(out.read_text(encoding="utf-8"))[2]["origen_clic"] == "cartera_lote"
    leads.export(rows, tmp_path / "leads.csv")
    assert (tmp_path / "leads.csv").read_text(encoding="utf-8").splitlines()[0] == ",".join(leads.EXPORT_FIELDS)


def test_d1_queries_via_wrangler_are_parsed_and_safe():
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        out = json.dumps([{"results": [{"email": "a@x.es"}], "success": True, "meta": {}}])
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    assert leads.d1_leads("radar-minimis", runner=runner) == [{"email": "a@x.es"}]
    assert calls[0][:6] == ["npx", "--yes", "wrangler@4", "d1", "execute", "radar-minimis"] and "--remote" in calls[0]
    leads.d1_delete_leads("radar-minimis", "A@X.es", runner=runner)
    assert calls[-1][-1] == "DELETE FROM leads WHERE email = 'a@x.es'"
    with pytest.raises(ValueError):
        leads.d1_delete_leads("radar-minimis", "x' OR 1=1 --@x.es", runner=runner)
    failing = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no autenticado")  # noqa: E731
    with pytest.raises(leads.D1Error, match="no autenticado"):
        leads.d1_leads("radar-minimis", runner=failing)


def test_cli_leads_summary_export_and_erasure(settings, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RM_DB_PATH", str(settings.db_path))
    with Store(settings.db_path) as store:
        store.add_lead("a@x.es", 30, CIF_A, "grupo_societario", leads.CONSENTIMIENTO_VERSION)
        store.incr_metric("calculo_minimis", "2099-01-01")
    out = tmp_path / "leads_validacion.json"
    assert data_engine.main(["leads", "--export", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "Envíos: 1" in printed and "grupo_societario 1" in printed and out.is_file()
    assert data_engine.main(["leads", "--borrar", "A@X.es"]) == 0
    with Store(settings.db_path) as store:
        assert store.leads() == []
