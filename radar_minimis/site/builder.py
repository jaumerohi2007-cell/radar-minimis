"""Generador pSEO estático: una ficha por convocatoria, hubs por territorio/beneficiario/finalidad, calculadora de
minimis, informe imprimible, panel demo para asesorías, sitemap y robots. Escribe en un directorio temporal y lo
intercambia al final, de modo que un fallo a mitad nunca publica un sitio a medias.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import ATTRIBUTION, DISCLAIMER, __version__
from ..bdns.models import Convocatoria
from ..config import Settings
from ..leads import EARLY_ACCESS_COPY, EARLY_ACCESS_TITLE
from ..matching import CompanyProfile, match
from ..minimis import (
    CRITERIO_ACUMULACION,
    PESCA_BASE_CEILING_EUR,
    RULES,
    SEMAFORO_AMBAR,
    SEMAFORO_ROJO,
    SINGLE_UNDERTAKING_NOTICE,
    Award,
    Regime,
    compute_headroom,
)
from ..privacy import cif_with_control
from ..store import Store

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"
PAGES_FILE_LIMIT = 20_000  # Cloudflare Pages Free: ficheros por despliegue
RESERVED_FILES = 500  # hubs, estáticos, sitemaps y páginas fijas
HUB_ITEMS = 300

# NUTS 2 de España: nombre estable para los hubs autonómicos aunque solo lleguen códigos provinciales.
NUTS2_NAMES = {
    "ES11": "Galicia",
    "ES12": "Principado de Asturias",
    "ES13": "Cantabria",
    "ES21": "País Vasco",
    "ES22": "Comunidad Foral de Navarra",
    "ES23": "La Rioja",
    "ES24": "Aragón",
    "ES30": "Comunidad de Madrid",
    "ES41": "Castilla y León",
    "ES42": "Castilla-La Mancha",
    "ES43": "Extremadura",
    "ES51": "Cataluña",
    "ES52": "Comunitat Valenciana",
    "ES53": "Illes Balears",
    "ES61": "Andalucía",
    "ES62": "Región de Murcia",
    "ES63": "Ciudad de Ceuta",
    "ES64": "Ciudad de Melilla",
    "ES70": "Canarias",
}

# NUTS 1 con una sola comunidad: se publican en el hub de esa comunidad.
_NUTS1_SINGLE = {"ES3": "ES30", "ES7": "ES70"}

GEN, AGR, PES = (
    "REG (UE) 2023/2831 de minimis, General",
    "REG (UE) 1408/2013 de minimis, Agrícola",
    ("REG (UE) 717/2014 de minimis, Pesca"),
)
# Panel demo para asesorías: empresas FICTICIAS (CIF sintéticos con dígito de control válido).
# (nombre, letra CIF, CNAE, NUTS3, provincia, [(meses atrás, importe, reglamento)])
DEMO_CLIENTES = [
    ("Panadería Ejemplo del Norte, SL", "B", "10", "ES111", "A Coruña", [(8, 12_000, GEN)]),
    ("Talleres Demo Levante, SL", "B", "45", "ES523", "Valencia", [(14, 30_500, GEN), (3, 15_000, GEN)]),
    ("Estudio Audiovisual Muestra, SL", "B", "59", "ES300", "Madrid", [(20, 98_000, GEN), (6, 60_000, GEN)]),
    ("Hotel Rural Ficticio, SL", "B", "55", "ES417", "Soria", [(30, 180_000, GEN), (2, 116_400, GEN)]),
    ("Consultora Prueba Digital, SL", "B", "62", "ES511", "Barcelona", []),
    ("Bodegas Imaginarias, SA", "A", "11", "ES230", "La Rioja", [(11, 210_000, GEN)]),
    ("Construcciones Ejemplo Sur, SL", "B", "41", "ES618", "Sevilla", [(25, 140_000, GEN), (9, 128_000, GEN)]),
    ("Transportes Demo Meseta, SL", "B", "49", "ES425", "Toledo", [(16, 88_000, GEN)]),
    ("Clínica Dental Muestra, SLP", "B", "86", "ES620", "Murcia", [(4, 31_200, GEN)]),
    ("Agroexplotación Ficticia, SL", "B", "01", "ES431", "Badajoz", [(10, 47_000, AGR)]),
    ("Conservas Demo Atlántico, SL", "B", "10", "ES114", "Pontevedra", [(18, 70_000, GEN), (5, 50_000, GEN)]),
    ("Academia Ejemplo Formación, SL", "B", "85", "ES243", "Zaragoza", [(7, 9_800, GEN)]),
    ("Imprenta Prueba Centro, SL", "B", "18", "ES300", "Madrid", [(28, 150_000, GEN), (12, 102_000, GEN)]),
    ("Cooperativa Demo Pesca, S. Coop.", "F", "03", "ES612", "Cádiz", [(13, 38_500, PES)]),
    ("Software Ficticio Canarias, SL", "B", "62", "ES701", "Las Palmas", [(33, 95_000, GEN), (1, 210_000, GEN)]),
]


def region_hub_key(code: str) -> tuple[str, str] | None:
    """Clasifica un código territorial de la BDNS en un hub; None si no merece hub propio."""
    code = (code or "").upper()
    if code.startswith("X"):  # "XXX"/"XXXX": fuera de Europa o todo el mundo
        return ("internacional", "XX")
    if code == "ES":
        return ("espana", "ES")
    if code in _NUTS1_SINGLE:
        return ("comunidad", _NUTS1_SINGLE[code])
    if code in NUTS2_NAMES:
        return ("comunidad", code)
    if len(code) == 5 and code[:4] in NUTS2_NAMES:
        return ("provincia", code)
    return None


def slugify(text: str, max_len: int = 80) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug[:max_len].rstrip("-") or "convocatoria"


def format_eur(value: float | None) -> str:
    if value is None:
        return "No publicado"
    return f"{value:,.0f}".replace(",", ".") + " €"


def format_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _months_before(d: date, months: int) -> date:
    year, month = divmod(d.year * 12 + d.month - 1 - months, 12)
    return date(year, month + 1, min(d.day, 28))


@dataclass(frozen=True, slots=True)
class Hub:
    path: str
    title: str
    intro: str
    kind: str
    items: tuple[Convocatoria, ...]


@dataclass
class BuildReport:
    convocatorias: int
    hubs: int
    files: int
    out_dir: Path

    def __str__(self) -> str:
        return f"{self.convocatorias} fichas, {self.hubs} hubs, {self.files} ficheros en {self.out_dir}"


class SiteBuilder:
    def __init__(self, settings: Settings, store: Store, *, today: date | None = None) -> None:
        self.settings = settings
        self.store = store
        self.today = today or date.today()
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATES),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["eur"] = format_eur
        self.env.filters["fecha"] = format_date
        self._sitemap: list[tuple[str, str]] = []
        self._files = 0

    # --- rutas ----------------------------------------------------------------------------------
    @staticmethod
    def conv_path(conv: Convocatoria) -> str:
        return f"/ayudas/{conv.codigo_bdns}-{slugify(conv.titulo, 70)}/"

    def url(self, path: str) -> str:
        return self.settings.site_url + path

    # --- construcción ---------------------------------------------------------------------------
    def build(self) -> BuildReport:
        out = self.settings.site_dir
        tmp = out.with_name(out.name + ".tmp")
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)

        max_conv = max(0, min(self.settings.site_max_pages, PAGES_FILE_LIMIT - RESERVED_FILES))
        items = self.store.convocatorias_for_site(self.today, self.settings.site_window_days, max_conv)
        convs = [c for c, _ in items]
        updated = (self.store.get_meta("last_sync_convocatorias") or self.today.isoformat())[:10]
        hubs = self._hubs(convs)
        hub_links = self._hub_links(hubs)
        s = self.settings
        base = {
            "site_url": s.site_url,
            "api_url": s.api_url,
            "leads_api_url": s.leads_api_url,
            "billing_mode": s.billing_mode,
            "checkout_url": s.stripe_payment_link,
            "free_group_max": s.free_group_max_cifs,
            "pro_slots": s.pro_linked_slots,
            "early_title": EARLY_ACCESS_TITLE,
            "early_copy": EARLY_ACCESS_COPY,
            "legal_owner": s.legal_owner,
            "privacy_email": s.privacy_email or s.contact_email,
            "google_site_verification": s.google_site_verification,
            "attribution": ATTRIBUTION,
            "disclaimer": DISCLAIMER,
            "unica_empresa": SINGLE_UNDERTAKING_NOTICE,
            "criterio_acumulacion": CRITERIO_ACUMULACION,
            "updated": updated,
            "today": self.today,
            "version": __version__,
        }

        for conv, upd in items:
            self._render(
                tmp,
                self.conv_path(conv),
                "convocatoria.html",
                lastmod=upd[:10],
                **base,
                conv=conv,
                estado=conv.estado(self.today),
                dias=conv.dias_para_cierre(self.today),
                links=hub_links.get(conv.codigo_bdns, []),
                jsonld=self._jsonld(conv),
            )
        for hub in hubs:
            self._render(
                tmp,
                hub.path,
                "hub.html",
                lastmod=updated,
                **base,
                hub=hub,
                estados={c.codigo_bdns: c.estado(self.today) for c in hub.items},
                conv_path=self.conv_path,
            )
        closing = sorted(
            (c for c in convs if c.dias_para_cierre(self.today) is not None), key=lambda c: c.fecha_fin_solicitud
        )[:HUB_ITEMS]
        closing_hub = Hub(
            "/ayudas/cierran-pronto/",
            f"Ayudas y subvenciones que cierran pronto ({self.today.year})",
            f"Las {len(closing)} convocatorias abiertas con el plazo más próximo, actualizadas a diario.",
            "cierre",
            tuple(closing),
        )
        self._render(
            tmp,
            closing_hub.path,
            "hub.html",
            lastmod=updated,
            **base,
            hub=closing_hub,
            estados={c.codigo_bdns: c.estado(self.today) for c in closing},
            conv_path=self.conv_path,
        )
        self._render(
            tmp,
            "/",
            "home.html",
            lastmod=updated,
            **base,
            closing=closing[:10],
            latest=convs[:20],
            hubs=[h for h in hubs if h.kind in ("comunidad", "beneficiario")],
            total=len(convs),
            conv_path=self.conv_path,
        )
        self._render(tmp, "/minimis/", "minimis.html", lastmod=updated, **base, rules=self._rules_table())
        self._render(tmp, "/minimis/informe/", "informe.html", sitemap=False, **base)
        self._render(
            tmp,
            "/asesorias/",
            "asesorias.html",
            lastmod=updated,
            **base,
            demo_json=self._json_script(self.demo_portfolio()),
            umbral_ambar=int(SEMAFORO_AMBAR * 100),
            umbral_rojo=int(SEMAFORO_ROJO * 100),
        )
        self._render(tmp, "/aviso-legal/", "aviso_legal.html", lastmod=updated, **base)
        self._render(tmp, "/404.html", "404.html", sitemap=False, **base)

        shutil.copytree(STATIC, tmp / "static")
        self._files += sum(1 for f in (tmp / "static").rglob("*") if f.is_file())
        self._write_text(tmp / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {self.url('/sitemap.xml')}\n")
        self._write_text(tmp / "_headers", self._headers())
        self._write_sitemaps(tmp)

        if out.exists():
            shutil.rmtree(out)
        tmp.rename(out)
        return BuildReport(convocatorias=len(items), hubs=len(hubs), files=self._files, out_dir=out)

    # --- datos de páginas especiales ------------------------------------------------------------
    def _rules_table(self) -> list[dict]:
        pesca = RULES[Regime.PESCA]
        fish = self.settings.fish_ceiling_eur
        return [
            {
                "nombre": "General",
                "tope": RULES[Regime.GENERAL].ceiling_eur,
                "periodo": "3 años móviles, fecha a fecha",
                "base": RULES[Regime.GENERAL].legal_basis,
                "nota": "Agrícola y pesca también suman contra este tope.",
            },
            {
                "nombre": "SIEG (servicios de interés económico general)",
                "tope": RULES[Regime.SIEG].ceiling_eur,
                "periodo": "3 años móviles, fecha a fecha",
                "base": RULES[Regime.SIEG].legal_basis,
                "nota": "Criterio prudente: general + SIEG ≤ 750.000 €.",
            },
            {
                "nombre": "Agrícola (producción primaria)",
                "tope": RULES[Regime.AGRICOLA].ceiling_eur,
                "periodo": "3 años móviles, fecha a fecha",
                "base": RULES[Regime.AGRICOLA].legal_basis,
                "nota": "",
            },
            {
                "nombre": "Pesca y acuicultura",
                "tope": fish,
                "periodo": "Ejercicio en curso y dos anteriores",
                "base": pesca.legal_basis,
                "nota": f"Régimen base {format_eur(PESCA_BASE_CEILING_EUR)}; España aplica {format_eur(40_000)} "
                "con registro central (RD 1139/2024).",
            },
        ]

    def demo_portfolio(self) -> dict:
        """15 empresas ficticias calculadas con el motor real + convocatorias reales abiertas que encajan."""
        open_convs = self.store.open_convocatorias(self.today, limit=3000)
        clientes = []
        for i, (name, letter, cnae, nuts, provincia, ayudas) in enumerate(DEMO_CLIENTES, start=1):
            cif = cif_with_control(letter, f"{9_100_000 + i * 37:07d}")
            awards = [
                Award(
                    f"demo-{i}-{j}", cif, name, _months_before(self.today, months), float(amount), reg, "Demostración"
                )
                for j, (months, amount, reg) in enumerate(ayudas)
            ]
            report = compute_headroom(awards, self.today, [cif], fish_ceiling_eur=self.settings.fish_ceiling_eur)
            data = report.to_dict()
            matches = match(open_convs, CompanyProfile(cif, frozenset({cnae}), nuts), self.today, limit=2)
            clientes.append(
                {
                    "nombre": name,
                    "cif": cif,
                    "cnae": cnae,
                    "provincia": provincia,
                    "usado_general_eur": data["regimenes"][0]["usado_eur"],
                    "margen_general_eur": data["margen_general_eur"],
                    "utilizacion": data["utilizacion"],
                    "semaforo": data["semaforo"],
                    "regimen_limitante": max(report.usages.values(), key=lambda u: u.utilization).regime.value,
                    "alertas": [
                        {
                            "codigo_bdns": m.convocatoria.codigo_bdns,
                            "titulo": m.convocatoria.titulo[:110],
                            "url": self.conv_path(m.convocatoria),
                            "cierre": format_date(m.convocatoria.fecha_fin_solicitud),
                        }
                        for m in matches
                    ],
                }
            )
        return {"fecha": self.today.isoformat(), "clientes": clientes, "convocatorias_abiertas": len(open_convs)}

    @staticmethod
    def _json_script(data: dict) -> str:
        """JSON seguro para incrustar en <script type="application/json"> (no ejecutable: compatible con la CSP)."""
        return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")

    # --- piezas ---------------------------------------------------------------------------------
    def _render(
        self, root: Path, path: str, template: str, *, sitemap: bool = True, lastmod: str | None = None, **ctx
    ) -> None:
        target = root / path.lstrip("/")
        if path.endswith("/"):
            target = target / "index.html"
        html = self.env.get_template(template).render(path=path, canonical=self.url(path), **ctx)
        self._write_text(target, html)
        if sitemap:
            self._sitemap.append((self.url(path), lastmod or self.today.isoformat()))

    def _write_text(self, target: Path, text: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self._files += 1

    def _hubs(self, convs: list[Convocatoria]) -> list[Hub]:
        groups: dict[tuple[str, str], list[Convocatoria]] = defaultdict(list)
        names: dict[tuple[str, str], str] = {}
        for c in convs:
            for code, name in c.regiones:
                key = region_hub_key(code)
                if key is None:
                    continue
                groups[key].append(c)
                label = {"comunidad": NUTS2_NAMES.get(key[1]), "espana": "España", "internacional": "el extranjero"}
                names.setdefault(key, label.get(key[0]) or (name.title() if name.isupper() else name))
                if key[0] == "provincia" and code[:4] in NUTS2_NAMES:  # la provincial cuenta para su comunidad
                    groups[("comunidad", code[:4])].append(c)
                    names.setdefault(("comunidad", code[:4]), NUTS2_NAMES[code[:4]])
            for tipo in c.tipos_beneficiario:
                groups[("beneficiario", tipo)].append(c)
                names.setdefault(("beneficiario", tipo), tipo.capitalize())
            if c.finalidad:
                groups[("finalidad", c.finalidad)].append(c)
                names.setdefault(("finalidad", c.finalidad), c.finalidad)
        hubs: list[Hub] = []
        for (kind, key), members in groups.items():
            name = names.get((kind, key)) or key
            unique = list({m.codigo_bdns: m for m in members}.values())
            unique.sort(key=lambda m: (m.estado(self.today) != "abierta", m.fecha_fin_solicitud or date.max))
            path, title, intro = self._hub_text(kind, key, name, len(unique))
            hubs.append(Hub(path, title, intro, kind, tuple(unique[:HUB_ITEMS])))
        hubs.sort(key=lambda h: (h.kind, h.title))
        return hubs

    def _hub_text(self, kind: str, key: str, name: str, n: int) -> tuple[str, str, str]:
        year = self.today.year
        if kind == "provincia":
            return (
                f"/ayudas/provincia/{slugify(name)}/",
                f"Ayudas y subvenciones en {name} ({year})",
                f"{n} convocatorias con ámbito en la provincia de {name}, actualizadas a diario desde la BDNS.",
            )
        if kind == "comunidad":
            return (
                f"/ayudas/comunidad/{slugify(name)}/",
                f"Ayudas y subvenciones en {name} ({year})",
                f"{n} convocatorias autonómicas, provinciales y locales en {name}.",
            )
        if kind == "espana":
            return ("/ayudas/espana/", f"Ayudas de ámbito estatal ({year})", f"{n} convocatorias de ámbito estatal.")
        if kind == "internacional":
            return (
                "/ayudas/internacional/",
                f"Ayudas con ámbito internacional ({year})",
                f"{n} convocatorias cuyo ámbito incluye países fuera de Europa o todo el mundo.",
            )
        if kind == "beneficiario":
            return (
                f"/ayudas/para/{slugify(key)}/",
                f"Ayudas para {name.lower()} ({year})",
                f"{n} convocatorias dirigidas a: {name.lower()}.",
            )
        return (
            f"/ayudas/finalidad/{slugify(key)}/",
            f"Ayudas de {name.lower()} ({year})",
            f"{n} convocatorias con finalidad «{name}».",
        )

    def _hub_links(self, hubs: list[Hub]) -> dict[str, list[tuple[str, str]]]:
        links: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for h in hubs:
            for c in h.items:
                links[c.codigo_bdns].append((h.path, h.title))
        return links

    def _jsonld(self, conv: Convocatoria) -> str:
        data = {
            "@context": "https://schema.org",
            "@type": "MonetaryGrant",
            "name": conv.titulo,
            "url": self.url(self.conv_path(conv)),
            "funder": {
                "@type": "GovernmentOrganization",
                "name": conv.organo_nivel3 or conv.organo_nivel2 or conv.organo_nivel1,
            },
            "sameAs": conv.url_oficial,
        }
        if conv.presupuesto_total:
            data["amount"] = {"@type": "MonetaryAmount", "currency": "EUR", "value": conv.presupuesto_total}
        return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    def _headers(self) -> str:
        origins = []
        for url in (self.settings.api_url, self.settings.leads_api_url):
            parsed = urlparse(url)
            if parsed.netloc:
                origins.append(f"{parsed.scheme}://{parsed.netloc}")
        csp = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            f"connect-src 'self' {' '.join(dict.fromkeys(origins))}"
        ).strip()
        return (
            "/*\n"
            "  X-Content-Type-Options: nosniff\n"
            "  Referrer-Policy: strict-origin-when-cross-origin\n"
            "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
            f"  Content-Security-Policy: {csp}\n"
            "/minimis/informe/*\n"
            "  X-Robots-Tag: noindex\n"
            "/static/*\n"
            "  Cache-Control: public, max-age=604800\n"
        )

    def _write_sitemaps(self, root: Path, per_file: int = 45_000) -> None:
        chunks = [self._sitemap[i : i + per_file] for i in range(0, len(self._sitemap), per_file)] or [[]]
        names = []
        for i, chunk in enumerate(chunks, start=1):
            body = "".join(f"<url><loc>{escape(loc)}</loc><lastmod>{mod}</lastmod></url>" for loc, mod in chunk)
            name = f"sitemap-{i}.xml"
            self._write_text(
                root / name,
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
            )
            names.append(name)
        index = "".join(f"<sitemap><loc>{escape(self.url('/' + n))}</loc></sitemap>" for n in names)
        self._write_text(
            root / "sitemap.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{index}</sitemapindex>',
        )


__all__ = ["BuildReport", "SiteBuilder", "slugify", "format_eur", "region_hub_key"]
