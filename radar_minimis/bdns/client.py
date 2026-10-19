"""Cliente HTTP educado de la API BDNS.

El aviso legal de la BDNS permite restringir el acceso "ante situaciones de manifiesto
abuso del servicio". Por eso: ritmo limitado, reintentos con backoff exponencial y un
User-Agent identificable con contacto.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from datetime import date

import httpx

log = logging.getLogger(__name__)

_RETRYABLE = {429, 500, 502, 503, 504}


class BDNSError(RuntimeError):
    pass


class RateLimiter:
    """Intervalo mínimo entre peticiones, seguro entre hilos."""

    def __init__(self, rate_per_sec: float) -> None:
        self._interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self._interval
        if delay > 0:
            time.sleep(delay)


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


class BDNSClient:
    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        rate_per_sec: float = 2.0,
        timeout_s: float = 60.0,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            transport=transport,
        )
        self._limiter = RateLimiter(rate_per_sec)
        self._max_retries = max_retries
        self._sleep = sleep

    def __enter__(self) -> BDNSClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict) -> dict:
        query = {"vpd": "GE", **params}
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._limiter.wait()
            try:
                resp = self._http.get(path, params=query)
            except httpx.TransportError as exc:  # timeouts, conexión
                last_error = exc
                retry_after = None
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code not in _RETRYABLE:
                    raise BDNSError(f"HTTP {resp.status_code} en {path}: {resp.text[:200]}")
                last_error = BDNSError(f"HTTP {resp.status_code} en {path}")
                retry_after = resp.headers.get("Retry-After")
            if attempt < self._max_retries:
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2.0**attempt)
                log.warning("BDNS %s falló (%s); reintento %d en %.0fs", path, last_error, attempt + 1, delay)
                self._sleep(delay)
        raise BDNSError(f"BDNS {path} sin respuesta tras {self._max_retries + 1} intentos: {last_error}")

    def _paginate(self, path: str, params: dict, page_size: int = 1000) -> Iterator[dict]:
        page = 0
        while True:
            data = self._get(path, {**params, "page": page, "pageSize": page_size})
            content = data.get("content") or []
            yield from content
            if data.get("last", True) or not content:
                return
            page += 1

    # --- Convocatorias -------------------------------------------------------------------------
    def search_convocatorias(self, desde: date, hasta: date) -> Iterator[dict]:
        """Filas resumen de convocatorias registradas entre dos fechas (incluidas)."""
        return self._paginate("/convocatorias/busqueda", {"fechaDesde": _fmt(desde), "fechaHasta": _fmt(hasta)})

    def get_convocatoria(self, codigo_bdns: str) -> dict:
        return self._get("/convocatorias", {"numConv": codigo_bdns})

    # --- Minimis -------------------------------------------------------------------------------
    def minimis_by_nif(self, nif: str) -> list[dict]:
        return list(self._paginate("/minimis/busqueda", {"nifCif": nif}, page_size=500))

    def minimis_by_grant_date(self, desde: date, hasta: date) -> Iterator[dict]:
        """El filtro por fecha de registro de la BDNS da timeout (probado): se filtra por fecha de concesión."""
        return self._paginate("/minimis/busqueda", {"fechaDesde": _fmt(desde), "fechaHasta": _fmt(hasta)})
