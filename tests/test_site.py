import json
from dataclasses import replace

from conftest import REF, conv_raw

from radar_minimis.bdns.models import Convocatoria
from radar_minimis.privacy import NifKind, classify
from radar_minimis.site import SiteBuilder, slugify


def _load(store, raws):
    with store.transaction():
        for raw in raws:
            store.upsert_convocatoria(Convocatoria.from_api(raw), raw)


def test_slugify():
    assert (
        slugify("CONV. AYUDAS SECTOR VACUNO — Mantequilla de Soria") == "conv-ayudas-sector-vacuno-mantequilla-de-soria"
    )
    assert slugify("") == "convocatoria"


def test_build_site_generates_pseo_assets(settings, store):
    _load(
        store,
        [
            conv_raw("900001", reglamento="REG (UE) 2023/2831 de minimis, General"),
            conv_raw("900002", "AYUDAS CERRADAS ANTIGUAS", fin="2026-03-01", recepcion="2026-02-01"),
            conv_raw("900003", "SUBVENCIONES ASOCIACIONES CULTURALES", regiones=("ES41 - CASTILLA Y LEÓN",)),
        ],
    )
    report = SiteBuilder(settings, store, today=REF).build()
    root = settings.site_dir
    assert report.convocatorias == 2  # la cerrada fuera de la ventana de 120 días no se publica
    page = (root / "ayudas" / "900001-ayudas-demo-para-pymes-audiovisuales" / "index.html").read_text(encoding="utf-8")
    assert "Intervención General de la Administración del Estado" in page
    assert "Comprobación previa de minimis" in page and "application/ld+json" in page
    assert "[Vigente]" in page and "[Sujeta a minimis]" in page
    other = next((root / "ayudas").glob("900003-*/index.html")).read_text(encoding="utf-8")
    assert "Comprobación previa de minimis" not in other
    for rel in (
        "index.html",
        "minimis/index.html",
        "aviso-legal/index.html",
        "condiciones/index.html",
        "static/fonts/inter-var.woff2",
        "static/fonts/ibm-plex-mono-400.woff2",
        "static/fonts/instrument-serif-400.woff2",
        "ayudas/cierran-pronto/index.html",
        "ayudas/provincia/soria/index.html",
        "ayudas/comunidad/castilla-y-leon/index.html",
        "robots.txt",
        "_headers",
        "sitemap.xml",
        "sitemap-1.xml",
        "static/minimis.js",
        "404.html",
    ):
        assert (root / rel).is_file(), rel
    sitemap = (root / "sitemap-1.xml").read_text(encoding="utf-8")
    assert "https://radar.test/ayudas/900001-ayudas-demo-para-pymes-audiovisuales/" in sitemap
    assert "connect-src 'self' https://api.radar.test" in (root / "_headers").read_text(encoding="utf-8")


def test_region_hub_keys_follow_real_bdns_codes():
    from radar_minimis.site.builder import region_hub_key

    assert region_hub_key("ES417") == ("provincia", "ES417")
    assert region_hub_key("ES41") == ("comunidad", "ES41")
    assert region_hub_key("ES3") == ("comunidad", "ES30")
    assert region_hub_key("ES") == ("espana", "ES")
    assert region_hub_key("XXXX") == region_hub_key("XXX") == ("internacional", "XX")
    assert region_hub_key("ES4") is None


def test_build_respects_page_cap(settings, store):
    _load(store, [conv_raw(str(900100 + i)) for i in range(5)])
    report = SiteBuilder(replace(settings, site_max_pages=2), store, today=REF).build()
    assert report.convocatorias == 2


def test_printable_report_page(settings, store):
    SiteBuilder(settings, store, today=REF).build()
    root = settings.site_dir
    page = (root / "minimis" / "informe" / "index.html").read_text(encoding="utf-8")
    assert 'id="inf-print"' in page and "/static/informe.js" in page and 'content="noindex"' in page
    assert 'data-pro-origen="informe_pdf"' in page and "Intervención General" in page
    css = (root / "static" / "style.css").read_text(encoding="utf-8")
    assert "@media print" in css and "size: A4" in css and "table-header-group" in css
    js = (root / "static" / "informe.js").read_text(encoding="utf-8")
    for label in (
        "Fecha de concesión",
        "Órgano convocante",
        "Código BDNS",
        "Importe equivalente",
        "Consulta a la BDNS (fecha y hora)",
        "fresco",
        "Borrador de declaración responsable",
        "N.º de control",
    ):
        assert label in js, label
    assert "informe/" not in (root / "sitemap-1.xml").read_text(encoding="utf-8")
    assert "/minimis/informe/*\n  X-Robots-Tag: noindex" in (root / "_headers").read_text(encoding="utf-8")


def test_calculator_page_has_group_slots_and_verified_ceilings(settings, store):
    SiteBuilder(settings, store, today=REF).build()
    page = (settings.site_dir / "minimis" / "index.html").read_text(encoding="utf-8")
    assert page.count('name="vinculada"') == 3
    assert page.count('data-pro-origen="grupo_societario"') == 2  # el 1.er vinculado es gratis (grupo de 2)
    for text in ("300.000 €", "750.000 €", "50.000 €", "40.000 €", "RD 1139/2024", "art. 2.2", "fecha a fecha"):
        assert text in page, text


def test_advisor_demo_panel(settings, store):
    _load(store, [conv_raw("900001", sectores=(("59.1", "Cine"),), regiones=("ES300 - Madrid",))])
    SiteBuilder(settings, store, today=REF).build()
    page = (settings.site_dir / "asesorias" / "index.html").read_text(encoding="utf-8")
    assert 'data-pro-origen="cartera_lote">Importar CSV de CIFs' in page and 'id="acceso-form"' in page
    assert 'data-pro-origen="alertas_cartera"' in page and "/static/asesorias.js" in page
    raw = page.split('<script type="application/json" id="demo-data">', 1)[1].split("</script>", 1)[0]
    demo = json.loads(raw)
    assert len(demo["clientes"]) == 15
    assert {c["semaforo"] for c in demo["clientes"]} == {"verde", "ambar", "rojo"}
    assert all(classify(c["cif"]) is NifKind.LEGAL_ENTITY for c in demo["clientes"])
    estudio = next(c for c in demo["clientes"] if c["cnae"] == "59")
    assert [a["codigo_bdns"] for a in estudio["alertas"]] == ["900001"]  # convocatoria real cruzada por el motor
    agro = next(c for c in demo["clientes"] if c["cnae"] == "01")
    assert agro["semaforo"] == "rojo" and agro["regimen_limitante"] == "agricola"  # 47.000 / 50.000


def test_modal_only_in_validation_mode(settings, stripe_settings, store):
    SiteBuilder(settings, store, today=REF).build()
    page = (settings.site_dir / "index.html").read_text(encoding="utf-8")
    assert 'id="pro-modal"' in page and "50% de descuento vitalicio (19 €/mes)" in page
    assert 'name="consentimiento"' in page and 'name="web"' in page and 'data-billing="validation"' in page
    SiteBuilder(stripe_settings, store, today=REF).build()
    page = (stripe_settings.site_dir / "index.html").read_text(encoding="utf-8")
    assert 'id="pro-modal"' not in page and 'data-checkout="https://buy.stripe.test/pro"' in page
    assert 'id="plan-modal"' in page and 'id="plan-pay"' in page and "19,00 €/mes" in page
    assert 'href="/condiciones/"' in page and 'data-pro-group-max="4"' in page


def test_public_base_url_and_search_console_meta(settings, store):
    prod = replace(settings, site_url="https://radar-minimis.pages.dev", google_site_verification="abc123")
    SiteBuilder(prod, store, today=REF).build()
    root = prod.site_dir
    home = (root / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://radar-minimis.pages.dev/">' in home
    assert '<meta name="google-site-verification" content="abc123">' in home
    assert "Sitemap: https://radar-minimis.pages.dev/sitemap.xml" in (root / "robots.txt").read_text(encoding="utf-8")
    assert "https://radar-minimis.pages.dev/sitemap-1.xml" in (root / "sitemap.xml").read_text(encoding="utf-8")
    assert "radarminimis.es" not in home


def test_editorial_design_rules(settings, store):
    """Sin emojis, degradados ni sombras; radios de 2 px como máximo; fuentes propias y cifras en monoespaciada."""
    import re

    _load(store, [conv_raw("900001", reglamento="REG (UE) 2023/2831 de minimis, General")])
    SiteBuilder(settings, store, today=REF).build()
    root = settings.site_dir
    emoji = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f]")
    for path in root.rglob("*"):
        if path.suffix in {".html", ".js", ".css"}:
            text = path.read_text(encoding="utf-8")
            assert not emoji.search(text), path
            assert "gradient" not in text and "box-shadow" not in text, path
    css = (root / "static" / "style.css").read_text(encoding="utf-8")
    assert all(int(px) <= 2 for px in re.findall(r"border-radius:\s*(\d+)px", css))
    assert "border-radius: 50%" not in css and "999px" not in css
    for family in ("Instrument Serif", "Inter", "IBM Plex Mono"):
        assert f'font-family: "{family}"' in css
    assert "tabular-nums" in css and "fonts.googleapis" not in css
    assert "#FAF9F5" in css and "#0F172A" in css and "#14532D" in css
    headers = (root / "_headers").read_text(encoding="utf-8")
    assert "font-src 'self'" in headers and "frame-ancestors 'none'" in headers


def test_contract_terms_page(settings, store):
    SiteBuilder(replace(settings, legal_nif="00000000T"), store, today=REF).build()
    page = (settings.site_dir / "condiciones" / "index.html").read_text(encoding="utf-8")
    for text in ("19,00 €/mes", "100 CIF", "Stripe", "portal de cliente", "00000000T", "Legislación española"):
        assert text in page, text
    legal = (settings.site_dir / "aviso-legal" / "index.html").read_text(encoding="utf-8")
    assert "Stripe Payments Europe" in legal and "SHA-256" in legal
