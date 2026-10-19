"""Alta automática de clientes: webhook de Stripe -> cuenta + API key -> email. Sin humanos.

La firma se verifica según el esquema documentado por Stripe (cabecera `Stripe-Signature`,
HMAC-SHA256 de "{timestamp}.{payload}" con el secreto del endpoint), sin depender del SDK.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from .store import Store

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Plan:
    code: str
    max_nifs: int


PLANS = {
    "asesoria_50": Plan("asesoria_50", 50),
    "asesoria_200": Plan("asesoria_200", 200),
    "pro_100": Plan("pro_100", 100),
}
DEFAULT_PLAN = "asesoria_50"

# Plan que se cobra en producción (Cloudflare + Stripe Checkout). La web, las Functions y el precio de Stripe
# deben coincidir: `STRIPE_PRICE_ID` apunta a un precio recurrente de PLAN_ASESORIAS["importe_cent"] al mes.
PLAN_ASESORIAS = {
    "codigo": "pro_100",
    "nombre": "Radar Minimis — Plan Asesorías Pro",
    "importe_cent": 1900,
    "precio": "19,00 €/mes",
    "max_cifs": 100,
    "max_vinculadas": 3,
    "dias_prueba": 14,  # prueba gratuita en Checkout (con tarjeta; sin cargo hasta el día 15)
}
# Importe cobrado (céntimos) -> plan: no depende de que el Payment Link propague `metadata`.
PLAN_BY_AMOUNT = {
    2900: "asesoria_50",
    29000: "asesoria_50",
    5900: "asesoria_200",
    59000: "asesoria_200",
    # Asesorías Pro (100 CIF): 19 €/mes acceso anticipado con 50 % vitalicio sobre la tarifa de 38 €/mes
    1900: "pro_100",
    3800: "pro_100",
    19000: "pro_100",
    38000: "pro_100",
}


def resolve_plan(session: dict) -> str:
    return (
        (session.get("metadata") or {}).get("plan") or PLAN_BY_AMOUNT.get(session.get("amount_total")) or DEFAULT_PLAN
    )


class SignatureError(ValueError):
    pass


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, *, tolerance_s: int = 300, now: float | None = None
) -> dict:
    if not secret:
        raise SignatureError("webhook sin secreto configurado")
    timestamp, signatures = None, []
    for part in (header or "").split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp or not timestamp.isdigit() or not signatures:
        raise SignatureError("cabecera Stripe-Signature mal formada")
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise SignatureError("firma no válida")
    if abs((now if now is not None else time.time()) - int(timestamp)) > tolerance_s:
        raise SignatureError("timestamp fuera de tolerancia")
    return json.loads(payload)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


class Mailer(Protocol):
    def send(self, to: str, subject: str, html: str) -> None: ...


class LogMailer:
    """Desarrollo: registra el correo en lugar de enviarlo."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, html: str) -> None:
        self.sent.append((to, subject, html))
        log.info("EMAIL (simulado) a %s: %s", to, subject)


class ResendMailer:
    def __init__(self, api_key: str, sender: str, *, timeout_s: float = 15.0) -> None:
        self._api_key, self._sender, self._timeout = api_key, sender, timeout_s

    def send(self, to: str, subject: str, html: str) -> None:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"from": self._sender, "to": [to], "subject": subject, "html": html},
            timeout=self._timeout,
        )
        resp.raise_for_status()


def handle_event(event: dict, store: Store, mailer: Mailer) -> str:
    """Procesa un evento verificado de Stripe de forma idempotente. Devuelve qué se hizo."""
    event_id = event.get("id", "")
    if not event_id:
        return "ignorado_sin_id"
    if store.event_processed(event_id):
        return "duplicado"
    kind = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    outcome = "ignorado"
    if kind == "checkout.session.completed":
        email = ((obj.get("customer_details") or {}).get("email") or obj.get("customer_email") or "").strip().lower()
        plan = resolve_plan(obj)
        if not email or plan not in PLANS:
            log.error("Checkout %s sin email o con plan desconocido (%r)", obj.get("id"), plan)
            outcome = "error_datos"
        else:
            api_key = "rm_" + secrets.token_urlsafe(32)
            _, created = store.upsert_account(email, plan, hash_api_key(api_key), obj.get("customer"))
            if created:
                mailer.send(
                    email,
                    "Tu acceso a Radar Minimis",
                    f"<p>Gracias. Tu plan <b>{plan}</b> está activo.</p>"
                    f"<p>Tu clave de API (guárdala, no se vuelve a mostrar): <code>{api_key}</code></p>",
                )
                outcome = "cuenta_creada"
            else:
                mailer.send(email, "Plan actualizado en Radar Minimis", f"<p>Tu plan ahora es <b>{plan}</b>.</p>")
                outcome = "cuenta_actualizada"
    elif kind == "customer.subscription.deleted" and obj.get("customer"):
        outcome = f"desactivadas_{store.deactivate_customer(obj['customer'])}"
    store.mark_event_processed(event_id)
    return outcome
