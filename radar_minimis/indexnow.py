"""IndexNow: avisa a Bing (y al resto de buscadores del protocolo) de las URL nuevas o cambiadas del sitemap.

La clave es pública por diseño: se publica en `/{clave}.txt` para demostrar la propiedad del dominio.
La primera ejecución envía todo el sitemap; las siguientes, solo lo modificado desde el último envío.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10_000  # máximo de URL por petición según el protocolo
META_KEY = "indexnow_enviado_hasta"
_URL_RE = re.compile(r"<url><loc>([^<]+)</loc><lastmod>([^<]+)</lastmod></url>")
KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def sitemap_urls(site_dir: Path, since: date | None = None) -> list[str]:
    """URL de los sitemaps generados con lastmod >= since (todas si since es None)."""
    urls: list[str] = []
    for sm in sorted(site_dir.glob("sitemap-*.xml")):
        for loc, mod in _URL_RE.findall(sm.read_text(encoding="utf-8")):
            if since is None or date.fromisoformat(mod[:10]) >= since:
                urls.append(loc.replace("&amp;", "&"))
    return urls


def submit(urls: list[str], *, key: str, site_url: str, client: httpx.Client) -> int:
    if not KEY_RE.fullmatch(key):
        raise ValueError("clave IndexNow no válida (8-128 caracteres alfanuméricos o guiones)")
    host = urlparse(site_url).netloc
    sent = 0
    for i in range(0, len(urls), BATCH):
        chunk = urls[i : i + BATCH]
        payload = {"host": host, "key": key, "keyLocation": f"{site_url}/{key}.txt", "urlList": chunk}
        resp = client.post(ENDPOINT, json=payload, timeout=60)
        # 200 = aceptado; 202 = aceptado, clave pendiente de validar
        if resp.status_code not in (200, 202):
            raise httpx.HTTPStatusError(f"IndexNow HTTP {resp.status_code}", request=resp.request, response=resp)
        sent += len(chunk)
    return sent
