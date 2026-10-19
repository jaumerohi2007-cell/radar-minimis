"""ETL incremental BDNS -> almacén local. Idempotente y reanudable: se puede cortar y relanzar."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from .bdns.client import BDNSError
from .bdns.models import Convocatoria, award_from_api
from .minimis import Award
from .store import Store

log = logging.getLogger(__name__)


class BDNSSource(Protocol):
    def search_convocatorias(self, desde: date, hasta: date) -> Iterable[dict]: ...
    def get_convocatoria(self, codigo_bdns: str) -> dict: ...
    def minimis_by_nif(self, nif: str) -> list[dict]: ...
    def minimis_by_grant_date(self, desde: date, hasta: date) -> Iterable[dict]: ...


@dataclass
class SyncReport:
    desde: date
    hasta: date
    vistas: int = 0
    nuevas: int = 0
    actualizadas: int = 0
    errores: int = 0
    pendientes: int = 0

    def __str__(self) -> str:
        return (
            f"{self.desde}..{self.hasta}: vistas={self.vistas} nuevas={self.nuevas} "
            f"actualizadas={self.actualizadas} errores={self.errores} pendientes={self.pendientes}"
        )


def date_windows(desde: date, hasta: date, days: int) -> list[tuple[date, date]]:
    """Ventanas [inicio, fin] de `days` días, de la más reciente a la más antigua."""
    windows: list[tuple[date, date]] = []
    end = hasta
    while end >= desde:
        start = max(desde, end - timedelta(days=days - 1))
        windows.append((start, end))
        end = start - timedelta(days=1)
    return windows


def sync_convocatorias(
    source: BDNSSource,
    store: Store,
    *,
    desde: date,
    hasta: date,
    refresh_since: date | None = None,
    max_details: int | None = None,
    window_days: int = 7,
) -> SyncReport:
    """Descarga el detalle de las convocatorias nuevas (y refresca las recientes) entre dos fechas.

    `max_details` acota el trabajo por ejecución; lo no procesado queda como `pendientes`
    y la siguiente ejecución lo recoge, porque solo se descargan códigos desconocidos.
    """
    report = SyncReport(desde, hasta)
    refresh = set(store.codigos_received_since(refresh_since)) if refresh_since else set()
    budget = max_details
    for w_start, w_end in date_windows(desde, hasta, window_days):
        try:
            rows = list(source.search_convocatorias(w_start, w_end))
        except BDNSError as exc:
            log.error("Búsqueda %s..%s fallida: %s", w_start, w_end, exc)
            report.errores += 1
            continue
        codigos = list(dict.fromkeys(str(r["numeroConvocatoria"]) for r in rows if r.get("numeroConvocatoria")))
        report.vistas += len(codigos)
        known = store.known_codigos(codigos)
        for codigo in (c for c in codigos if c not in known or c in refresh):
            if budget is not None and budget <= 0:
                report.pendientes += 1
                continue
            try:
                raw = source.get_convocatoria(codigo)
                conv = Convocatoria.from_api(raw)
                if not conv.codigo_bdns:
                    raise ValueError("respuesta sin codigoBDNS")
            except (BDNSError, ValueError, KeyError, TypeError) as exc:
                log.warning("Convocatoria %s no procesada: %s", codigo, exc)
                report.errores += 1
                continue
            with store.transaction():
                store.upsert_convocatoria(conv, raw)
            if codigo in known:
                report.actualizadas += 1
            else:
                report.nuevas += 1
            if budget is not None:
                budget -= 1
        log.info("Ventana %s..%s: %d convocatorias", w_start, w_end, len(codigos))
    store.record_sync("convocatorias", desde, hasta, report.vistas, report.nuevas, report.errores)
    return report


def lookup_minimis(
    source: BDNSSource, store: Store, nif: str, *, ttl_hours: int, max_age: timedelta | None = None
) -> list[Award]:
    """Concesiones de minimis de un CIF, consultando la BDNS como mucho una vez por `ttl_hours`."""
    if not store.lookup_is_fresh(nif, max_age if max_age is not None else timedelta(hours=ttl_hours)):
        rows = source.minimis_by_nif(nif)
        # El filtro `nifCif` podría devolver coincidencias parciales: se exige igualdad exacta.
        awards = [a for a in (award_from_api(r) for r in rows) if a is not None and a.nif == nif]
        store.upsert_awards(awards)
        store.mark_lookup(nif, len(awards))
    return store.awards_for([nif])


def sync_portfolio_awards(source: BDNSSource, store: Store, *, today: date, days: int = 45) -> list[Award]:
    """Busca concesiones recientes de los CIF vigilados y devuelve solo las que no se conocían.

    La ventana móvil de `days` días absorbe el retraso entre concesión y registro en la BDNS.
    """
    nifs = store.all_portfolio_nifs()
    if not nifs:
        return []
    new_ids: list[str] = []
    for w_start, w_end in date_windows(today - timedelta(days=days), today, 7):
        batch = [
            a
            for a in (award_from_api(r) for r in source.minimis_by_grant_date(w_start, w_end))
            if a is not None and a.nif in nifs
        ]
        new_ids += store.upsert_awards(batch)
    store.record_sync("minimis_cartera", today - timedelta(days=days), today, len(nifs), len(new_ids), 0)
    wanted = set(new_ids)
    return [a for a in store.awards_for(nifs) if a.award_id in wanted]
