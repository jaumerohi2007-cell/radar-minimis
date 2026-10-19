import hashlib
import hmac

import pytest

from radar_minimis.billing import LogMailer, SignatureError, handle_event, resolve_plan, verify_stripe_signature


def _header(body: bytes, ts: int, secret: str = "whsec_test") -> str:
    return f"t={ts},v1={hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()}"


def test_signature_ok_and_failures():
    body = b'{"id": "evt_1"}'
    assert verify_stripe_signature(body, _header(body, 1000), "whsec_test", now=1000)["id"] == "evt_1"
    with pytest.raises(SignatureError):
        verify_stripe_signature(body, _header(body, 1000, "otro"), "whsec_test", now=1000)
    with pytest.raises(SignatureError):
        verify_stripe_signature(body, _header(body, 1000), "whsec_test", now=2000)  # fuera de tolerancia
    with pytest.raises(SignatureError):
        verify_stripe_signature(body, "basura", "whsec_test", now=1000)
    with pytest.raises(SignatureError):
        verify_stripe_signature(body, _header(body, 1000), "", now=1000)


def test_subscription_lifecycle(store):
    mailer = LogMailer()
    created = {
        "id": "evt_a",
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_9", "customer_details": {"email": "x@demo.test"}, "metadata": {}}},
    }
    assert handle_event(created, store, mailer) == "cuenta_creada"
    renewed = {**created, "id": "evt_b"}
    assert handle_event(renewed, store, mailer) == "cuenta_actualizada"
    deleted = {"id": "evt_c", "type": "customer.subscription.deleted", "data": {"object": {"customer": "cus_9"}}}
    assert handle_event(deleted, store, mailer) == "desactivadas_1"
    assert (
        handle_event(
            {
                "id": "evt_d",
                "type": "checkout.session.completed",
                "data": {"object": {"metadata": {"plan": "inexistente"}}},
            },
            store,
            mailer,
        )
        == "error_datos"
    )


def test_resolve_plan_prefers_metadata_then_amount():
    assert resolve_plan({"metadata": {"plan": "asesoria_200"}, "amount_total": 2900}) == "asesoria_200"
    assert resolve_plan({"metadata": {}, "amount_total": 59000}) == "asesoria_200"
    assert resolve_plan({"amount_total": 1234}) == "asesoria_50"


def test_pro_plan_from_early_access_amount():
    assert resolve_plan({"amount_total": 1900}) == "pro_100"
    assert resolve_plan({"amount_total": 3800}) == "pro_100"
