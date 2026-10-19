from datetime import date

from conftest import CIF_A, REF, conv_raw, minimis_raw

from radar_minimis.bdns.models import Convocatoria, award_from_api


def test_convocatoria_from_api():
    conv = Convocatoria.from_api(conv_raw())
    assert conv.codigo_bdns == "900001"
    assert conv.regiones == (("ES417", "Soria"),)
    assert conv.sectores[0][0] == "59.1"
    assert conv.presupuesto_total == 30000
    assert conv.estado(REF) == "abierta"
    assert conv.dias_para_cierre(REF) == 28
    assert conv.url_oficial.endswith("/convocatoria/900001")
    assert not conv.is_minimis
    assert Convocatoria.from_api(conv_raw(reglamento="REG (UE) 2023/2831 de minimis, General")).is_minimis
    # Forma real observada en la API el 19-10-2026: objeto con "descripcion".
    real = conv_raw(reglamento={"descripcion": "REG (UE) 2023/2831 de minimis, General", "orden": None})
    assert Convocatoria.from_api(real).reglamento.startswith("REG (UE) 2023/2831")
    assert Convocatoria.from_api(real).is_minimis


def test_estado_variants():
    assert Convocatoria.from_api(conv_raw(fin="2026-10-01")).estado(REF) == "cerrada"
    assert Convocatoria.from_api(conv_raw(inicio="2026-11-01")).estado(REF) == "proxima"
    assert Convocatoria.from_api(conv_raw(inicio=None, fin=None)).estado(REF) == "sin_plazo"


def test_from_api_tolerates_missing_fields():
    conv = Convocatoria.from_api({"codigoBDNS": "1", "descripcion": "X"})
    assert conv.titulo == "X" and conv.regiones == () and conv.fecha_fin_solicitud is None


def test_award_from_api_keeps_only_legal_entities():
    award = award_from_api(minimis_raw(10, CIF_A, "2026-10-15", 19200))
    assert award is not None and award.nif == CIF_A and award.sector_cnae == "59"
    assert award.granted_on == date(2026, 10, 15) and award.amount_eur == 19200
    assert award_from_api(minimis_raw(11, "12345678Z", "2026-10-15", 100)) is None  # persona física
    assert award_from_api(minimis_raw(12, "B12345675", "2026-10-15", 100)) is None  # control inválido
