"""Alertas de cartera: una concesión de minimis nueva de un cliente vigilado -> email a su asesoría."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from html import escape

from .billing import Mailer
from .minimis import Award
from .site.builder import format_eur
from .store import Store


def notify_new_awards(store: Store, mailer: Mailer, awards: Iterable[Award]) -> int:
    """Envía un único email por cuenta con todas sus concesiones nuevas. Devuelve emails enviados."""
    awards = list(awards)
    watchers = store.watchers({a.nif for a in awards})
    per_email: dict[str, list[Award]] = defaultdict(list)
    for a in awards:
        for email in watchers.get(a.nif, ()):
            per_email[email].append(a)
    for email, items in per_email.items():
        rows = "".join(
            f"<li><b>{escape(a.nif)}</b> {escape(a.beneficiary)}: {format_eur(a.amount_eur)} "
            f"({escape(a.regulation)}) concedida el {a.granted_on:%d/%m/%Y} por {escape(a.grantor)}</li>"
            for a in sorted(items, key=lambda x: x.granted_on, reverse=True)
        )
        mailer.send(
            email,
            f"Radar Minimis: {len(items)} concesión(es) nueva(s) en tu cartera",
            f"<p>Se han registrado en la BDNS nuevas ayudas de minimis de tus clientes:</p><ul>{rows}</ul>"
            "<p>Su margen disponible se ha actualizado en tu panel.</p>",
        )
    return len(per_email)
