"""Fixtures sintéticos con la misma forma que las respuestas reales de la API BDNS.

Los CIF de prueba tienen dígito de control válido (calculado a mano con el algoritmo oficial)
pero no corresponden a datos reales de la BDNS.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from radar_minimis.config import Settings
from radar_minimis.store import Store

REF = date(2026, 10, 19)
CIF_A = "B12345674"
CIF_B = "A11111119"
CIF_C = "B00000000"
PYME = "PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA"
GEN = "REG (UE) 2023/2831 de minimis, General"


def conv_raw(
    codigo: str = "900001",
    titulo: str = "AYUDAS DEMO PARA PYMES AUDIOVISUALES",
    *,
    inicio: str | None = "2026-10-17",
    fin: str | None = "2026-11-16",
    recepcion: str = "2026-10-15",
    sectores=(("59.1", "Actividades cinematográficas, de vídeo y de programas de televisión"),),
    regiones=("ES417 - Soria",),
    tipos=(PYME,),
    reglamento: str | dict | None = None,
    presupuesto: float | None = 30000,
) -> dict:
    return {
        "id": int(codigo),
        "organo": {
            "nivel1": "LOCAL",
            "nivel2": "DIPUTACIÓN PROV. DE SORIA",
            "nivel3": "DIPUTACIÓN PROVINCIAL DE SORIA",
        },
        "sedeElectronica": None,
        "codigoBDNS": codigo,
        "fechaRecepcion": recepcion,
        "instrumentos": [{"descripcion": "SUBVENCIÓN Y ENTREGA DINERARIA SIN CONTRAPRESTACIÓN "}],
        "tipoConvocatoria": "Concurrencia competitiva - canónica",
        "presupuestoTotal": presupuesto,
        "mrr": False,
        "descripcion": titulo,
        "descripcionLeng": None,
        "tiposBeneficiarios": [{"descripcion": t} for t in tipos],
        "sectores": [{"codigo": c, "descripcion": d} for c, d in sectores],
        "regiones": [{"descripcion": r} for r in regiones],
        "descripcionFinalidad": "Industria y Energía",
        "descripcionBasesReguladoras": "Ordenanza general de subvenciones (demo)",
        "urlBasesReguladoras": "https://example.org/bases.pdf",
        "sePublicaDiarioOficial": True,
        "abierto": False,
        "fechaInicioSolicitud": inicio,
        "fechaFinSolicitud": fin,
        "textInicio": "Al día siguiente de la publicación",
        "textFin": "20 días hábiles",
        "ayudaEstado": None,
        "urlAyudaEstado": None,
        "fondos": [],
        "reglamento": reglamento,
        "objetivos": [],
        "sectoresProductos": [],
        "documentos": [{"id": 1, "descripcion": "Texto de la convocatoria", "nombreFic": "demo.pdf"}],
        "anuncios": [],
        "advertencia": "La reutilización de los datos ... (texto de la API)",
    }


def minimis_raw(
    id_: int,
    nif: str,
    fecha: str,
    importe: float,
    *,
    reglamento: str = GEN,
    sector: str = "59 - Producción cinematográfica, de vídeo y de programas de televisión",
    convocante: str = "AUTONOMICA COMUNIDAD DEMO",
    num: str = "892429",
) -> dict:
    return {
        "idConcesion": id_,
        "numeroConvocatoria": num,
        "idConvocatoria": 1,
        "idPersona": 1,
        "codigoConcesion": f"SB{id_}",
        "convocante": convocante,
        "reglamento": reglamento,
        "sectorProducto": None,
        "instrumento": "SUBVENCIÓN y ENTREGA DINERARIA SIN CONTRAPRESTACIÓN ",
        "fechaConcesion": fecha,
        "fechaRegistro": fecha,
        "beneficiario": f"{nif} EMPRESA DEMO, SL",
        "sectorActividad": sector,
        "ayudaEquivalente": importe,
    }


class FakeSource:
    """Implementa el protocolo BDNSSource en memoria y cuenta las llamadas."""

    def __init__(self, convocatorias=(), minimis=()):
        self.convocatorias = {c["codigoBDNS"]: c for c in convocatorias}
        self.minimis = list(minimis)
        self.calls = {"search": 0, "detail": 0, "nif": 0, "grant_date": 0}

    def search_convocatorias(self, desde, hasta):
        self.calls["search"] += 1
        return [
            {"numeroConvocatoria": c["codigoBDNS"]}
            for c in self.convocatorias.values()
            if desde.isoformat() <= c["fechaRecepcion"] <= hasta.isoformat()
        ]

    def get_convocatoria(self, codigo):
        self.calls["detail"] += 1
        return self.convocatorias[codigo]

    def minimis_by_nif(self, nif):
        self.calls["nif"] += 1
        return [m for m in self.minimis if m["beneficiario"].startswith(nif[:6])]  # simula coincidencia parcial

    def minimis_by_grant_date(self, desde, hasta):
        self.calls["grant_date"] += 1
        return [m for m in self.minimis if desde.isoformat() <= m["fechaConcesion"] <= hasta.isoformat()]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=tmp_path / "radar.db",
        site_dir=tmp_path / "site",
        site_url="https://radar.test",
        api_url="https://api.radar.test",
        contact_email="test@radar.test",
        bdns_base_url="http://bdns.invalid",
        bdns_rate_per_sec=0,
        bdns_timeout_s=5,
        minimis_cache_ttl_h=24,
        site_max_pages=1000,
        site_window_days=120,
        free_lookups_per_day=3,
        stripe_webhook_secret="whsec_test",
        resend_api_key="",
        mail_from="test@radar.test",
        allowed_origins=("https://radar.test",),
    )


@pytest.fixture
def store(settings):
    s = Store(settings.db_path)
    yield s
    s.close()


@pytest.fixture
def stripe_settings(settings) -> Settings:
    return replace(settings, billing_mode="stripe", stripe_payment_link="https://buy.stripe.test/pro")
