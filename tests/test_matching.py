from datetime import date

from conftest import CIF_A, REF, conv_raw

from radar_minimis.bdns.models import Convocatoria
from radar_minimis.matching import CompanyProfile, match, profile_from_awards
from radar_minimis.minimis import Award


def test_profile_infers_cnae_from_awards():
    awards = [
        Award("1", CIF_A, "X", date(2026, 1, 1), 100, "REG", sector_cnae="59"),
        Award("2", "A11111119", "Y", date(2026, 1, 1), 100, "REG", sector_cnae="10"),
    ]
    assert profile_from_awards(CIF_A, awards, nuts="es417").cnae_divisions == {"59"}
    assert profile_from_awards(CIF_A, awards, nuts="es417").nuts == "ES417"


def test_match_rules():
    soria_audiovisual = Convocatoria.from_api(conv_raw("1"))
    closed = Convocatoria.from_api(conv_raw("2", fin="2026-10-01"))
    any_sector = Convocatoria.from_api(conv_raw("3", sectores=(), regiones=("ES41 - CASTILLA Y LEÓN",)))
    convs = [soria_audiovisual, closed, any_sector]

    in_soria = CompanyProfile(CIF_A, frozenset({"59"}), "ES417")
    codes = [m.convocatoria.codigo_bdns for m in match(convs, in_soria, REF)]
    assert codes == ["1", "3"]  # el cerrado queda fuera; el específico puntúa más

    assert [
        m.convocatoria.codigo_bdns for m in match(convs, CompanyProfile(CIF_A, frozenset({"59"}), "ES30"), REF)
    ] == []
    other_sector = CompanyProfile(CIF_A, frozenset({"10"}), "ES417")
    assert [m.convocatoria.codigo_bdns for m in match(convs, other_sector, REF)] == ["3"]
    worldwide = Convocatoria.from_api(conv_raw("4", sectores=(), regiones=("XXXX - TODO EL MUNDO",)))
    assert [m.convocatoria.codigo_bdns for m in match([worldwide], in_soria, REF)] == ["4"]
    best = match(convs, in_soria, REF)[0]
    assert "Coincide con tu actividad (CNAE)" in best.motivos
