import hashlib
import hmac
import json
import re
import time
from datetime import datetime

import pytest
from conftest import CIF_A, CIF_B, CIF_C, REF, FakeSource, conv_raw, minimis_raw
from fastapi.testclient import TestClient

from radar_minimis.api import create_app
from radar_minimis.api.app import RateLimiter
from radar_minimis.bdns.models import Convocatoria
from radar_minimis.billing import LogMailer
from radar_minimis.leads import EARLY_ACCESS_COPY
from radar_minimis.store import Store

AWARDS = [
    minimis_raw(1, CIF_A, "2025-05-01", 100_000),
    minimis_raw(2, CIF_B, "2026-01-15", 20_000),
    minimis_raw(3, CIF_C, "2026-03-01", 30_000),
]


def make(settings, source=None, limiter=None, mailer=None):
    app = create_app(
        settings,
        source=source or FakeSource(minimis=AWARDS),
        mailer=mailer or LogMailer(),
        today=lambda: REF,
        limiter=limiter or RateLimiter(per_minute=100, per_day=100),
    )
    return TestClient(app)


def signed(payload: dict, secret: str = "whsec_test") -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


def lead(**overrides):
    payload = {
        "email": "Gestor@Asesoria.test",
        "num_cifs_estimados": 40,
        "origen_clic": "grupo_societario",
        "cif_consultado": CIF_A,
        "consentimiento": True,
        "web": "",
    }
    payload.update(overrides)
    return payload


def test_health_reports_billing_mode(settings):
    data = make(settings).get("/api/health").json()
    assert data["ok"] is True and data["modo"] == "validation"


def test_minimis_single_and_two_cif_group_are_free(settings):
    client = make(settings)
    single = client.get(f"/api/minimis/{CIF_A}").json()
    assert single["margen_general_eur"] == 200_000
    assert "Intervención General" in single["atribucion"]
    assert single["aviso_unica_empresa"].startswith("«Única empresa» (art. 2.2")
    group = client.get(f"/api/minimis/{CIF_A}", params={"vinculadas": CIF_B}).json()
    assert group["margen_general_eur"] == 180_000 and group["cifs"] == [CIF_A, CIF_B]


def test_report_fields_bdns_timestamp_and_fresh_refetch(settings):
    source = FakeSource(minimis=AWARDS)
    client = make(settings, source=source)
    data = client.get(f"/api/minimis/{CIF_A}").json()
    stamp = data["consultas_bdns"][0]
    assert stamp["cif"] == CIF_A and stamp["n_concesiones"] == 1
    assert datetime.fromisoformat(stamp["consultado_en"]).tzinfo is not None
    assert data["beneficiarios"][CIF_A] == "EMPRESA DEMO, SL"
    assert data["concesiones"][0]["concedente"] and data["concesiones"][0]["codigo_bdns"] == "892429"
    assert {r["regimen"] for r in data["regimenes"]} >= {"general", "sieg"}
    client.get(f"/api/minimis/{CIF_A}")
    assert source.calls["nif"] == 1  # caché de 24 h
    client.get(f"/api/minimis/{CIF_A}", params={"fresco": "1"})
    assert source.calls["nif"] == 1  # «fresco» admite datos de hace menos de 10 minutos


def test_reference_date_flag(settings):
    data = make(settings).get(f"/api/minimis/{CIF_A}", params={"fecha": "2028-05-02"}).json()
    assert data["fecha_referencia_indicada"] is True and data["ventana_desde"] == "2025-05-03"
    assert data["margen_general_eur"] == 300_000  # la concesión de 01/05/2025 ya está fuera de la ventana


def test_validation_mode_gates_large_groups_with_early_access(settings):
    resp = make(settings).get(f"/api/minimis/{CIF_A}", params={"vinculadas": f"{CIF_B},{CIF_C}"})
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert detail["codigo"] == "acceso_anticipado" and detail["origen"] == "grupo_societario"
    assert detail["mensaje"] == EARLY_ACCESS_COPY and "19 €/mes" in detail["mensaje"]


def test_validation_mode_disables_portfolio_and_stripe(settings):
    client = make(settings)
    resp = client.get("/api/cartera", headers={"X-API-Key": "rm_cualquiera"})
    assert resp.status_code == 402 and resp.json()["detail"]["origen"] == "cartera_lote"
    assert client.post("/api/cartera", json={"cifs": [CIF_A]}).status_code == 402
    body, header = signed({"id": "evt_x", "type": "checkout.session.completed"})
    assert client.post("/webhooks/stripe", content=body, headers={"Stripe-Signature": header}).status_code == 404


@pytest.mark.parametrize(("cif", "fragment"), [("12345678Z", "persona física"), ("B12345675", "no es un CIF válido")])
def test_rejects_natural_persons_and_invalid(settings, cif, fragment):
    resp = make(settings).get(f"/api/minimis/{cif}")
    assert resp.status_code == 422 and fragment in resp.json()["detail"]


def test_free_daily_quota(settings):
    client = make(settings, limiter=RateLimiter(per_minute=100, per_day=2))
    assert [client.get(f"/api/minimis/{CIF_A}").status_code for _ in range(3)] == [200, 200, 429]


def test_encaje(settings):
    with Store(settings.db_path) as store, store.transaction():
        raw = conv_raw("900001")
        store.upsert_convocatoria(Convocatoria.from_api(raw), raw)
    data = make(settings).get(f"/api/encaje/{CIF_A}", params={"provincia": "ES417"}).json()
    assert data["cnae_inferido"] == ["59"]
    assert [c["codigo_bdns"] for c in data["convocatorias"]] == ["900001"]


# --- Lista de espera y métricas del embudo -----------------------------------------------------------
def test_waitlist_stores_lead_and_counts_conversion(settings):
    client = make(settings)
    client.get(f"/api/minimis/{CIF_A}")
    resp = client.post("/api/waitlist", json=lead())
    assert resp.status_code == 201 and resp.json()["ok"] is True
    with Store(settings.db_path) as store:
        rows = store.leads()
        events = {m["event"]: m["count"] for m in store.metrics("2000-01-01")}
    assert rows == [
        {
            "email": "gestor@asesoria.test",
            "num_cifs_estimados": 40,
            "cif_consultado": CIF_A,
            "origen_clic": "grupo_societario",
            "timestamp": rows[0]["timestamp"],
        }
    ]
    assert events == {"calculo_minimis": 1, "lead_grupo_societario": 1}


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"email": "no-es-un-email"}, "email"),
        ({"consentimiento": False}, "consentimiento"),
        ({"num_cifs_estimados": 0}, "entre 1"),
        ({"num_cifs_estimados": "muchas"}, "cuántas empresas"),
        ({"origen_clic": "otro"}, "Origen"),
    ],
)
def test_waitlist_validation(settings, overrides, fragment):
    resp = make(settings).post("/api/waitlist", json=lead(**overrides))
    assert resp.status_code == 422 and fragment in resp.json()["detail"]


def test_waitlist_never_stores_natural_person_ids_and_ignores_bots(settings):
    client = make(settings)
    assert client.post("/api/waitlist", json=lead(cif_consultado="12345678Z")).status_code == 201
    assert client.post("/api/waitlist", json=lead(email="bot@spam.test", web="http://spam")).status_code == 201
    with Store(settings.db_path) as store:
        rows = store.leads()
    assert [(r["email"], r["cif_consultado"]) for r in rows] == [("gestor@asesoria.test", None)]


def test_evento_whitelist(settings):
    client = make(settings)
    assert client.post("/api/evento", json={"tipo": "modal_cartera_lote"}).status_code == 204
    assert client.post("/api/evento", json={"tipo": "drop table"}).status_code == 422
    with Store(settings.db_path) as store:
        assert store.metrics("2000-01-01") == [{"day": REF.isoformat(), "event": "modal_cartera_lote", "count": 1}]


# --- BILLING_MODE=stripe: el código de Stripe sigue intacto ----------------------------------------
def test_stripe_mode_requires_webhook_secret(stripe_settings):
    from dataclasses import replace

    with pytest.raises(ValueError, match="RM_STRIPE_WEBHOOK_SECRET"):
        create_app(replace(stripe_settings, stripe_webhook_secret=""), source=FakeSource())


def test_stripe_mode_free_users_get_checkout_link(stripe_settings):
    resp = make(stripe_settings).get(f"/api/minimis/{CIF_A}", params={"vinculadas": f"{CIF_B},{CIF_C}"})
    assert resp.status_code == 402
    assert resp.json()["detail"] == {
        "codigo": "requiere_plan",
        "origen": "grupo_societario",
        "checkout_url": "https://buy.stripe.test/pro",
        "mensaje": "Función del plan Asesorías Pro.",
    }


def test_checkout_webhook_provisions_account_end_to_end(stripe_settings):
    mailer = LogMailer()
    client = make(stripe_settings, mailer=mailer)
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_1",
                "customer": "cus_1",
                "customer_details": {"email": "Asesoria@Demo.test"},
                "amount_total": 1900,
            }
        },
    }
    body, header = signed(event)
    resp = client.post("/webhooks/stripe", content=body, headers={"Stripe-Signature": header})
    assert resp.json()["resultado"] == "cuenta_creada"
    api_key = re.search(r"rm_[A-Za-z0-9_\-]+", mailer.sent[0][2]).group(0)
    again = client.post("/webhooks/stripe", content=body, headers={"Stripe-Signature": header})
    assert again.json()["resultado"] == "duplicado"

    headers = {"X-API-Key": api_key}
    group = client.get(f"/api/minimis/{CIF_A}", params={"vinculadas": f"{CIF_B},{CIF_C}"}, headers=headers)
    assert group.status_code == 200 and group.json()["margen_general_eur"] == 150_000
    assert client.post("/api/cartera", json={"cifs": [CIF_A, CIF_B]}, headers=headers).json()["total"] == 2
    cartera = client.get("/api/cartera", headers=headers).json()
    assert cartera["plan"] == "pro_100" and cartera["max_cifs"] == 100
    assert {e["cif"]: e["margen_general_eur"] for e in cartera["empresas"]} == {CIF_A: 200_000, CIF_B: 280_000}
    assert client.get("/api/cartera", headers={"X-API-Key": "rm_falsa"}).status_code == 401


def test_webhook_rejects_bad_signature(stripe_settings):
    body, _ = signed({"id": "evt_x", "type": "checkout.session.completed"})
    resp = make(stripe_settings).post("/webhooks/stripe", content=body, headers={"Stripe-Signature": "t=1,v1=dead"})
    assert resp.status_code == 400
