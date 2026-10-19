from datetime import date, timedelta

import pytest

from radar_minimis.minimis import (
    RULES,
    SINGLE_UNDERTAKING_NOTICE,
    Award,
    Regime,
    Window,
    classify_regulation,
    compute_headroom,
    semaforo,
    three_years_before,
    window_start,
)

REF = date(2026, 10, 19)
GEN = "REG (UE) 2023/2831 de minimis, General"
AGR = "REG (UE) 1408/2013 de minimis, Agrícola"
OLD = "REG (UE) 1407/2013 de minimis, General"
PES = "REG (UE) 717/2014 de minimis, Pesca"
SIEG = "REG (UE) 2023/2832 de minimis, SIEG"
A, B, C = "B12345674", "A11111119", "B00000000"


def aw(i, d, amount, reg=GEN, nif=A):
    return Award(str(i), nif, "EMPRESA DEMO", d, amount, reg, grantor="DEMO")


@pytest.mark.parametrize(
    ("text", "regime"),
    [
        (GEN, Regime.GENERAL),
        (OLD, Regime.GENERAL),
        (AGR, Regime.AGRICOLA),
        (PES, Regime.PESCA),
        (SIEG, Regime.SIEG),
        ("", Regime.DESCONOCIDO),
        (None, Regime.DESCONOCIDO),
    ],
)
def test_classify_regulation(text, regime):
    assert classify_regulation(text) is regime


def test_verified_ceilings():
    assert RULES[Regime.GENERAL].ceiling_eur == 300_000
    assert RULES[Regime.SIEG].ceiling_eur == 750_000
    assert RULES[Regime.AGRICOLA].ceiling_eur == 50_000
    assert RULES[Regime.PESCA].ceiling_eur == 40_000  # España: RD 1139/2024 (art. 3.2 bis Reg. 717/2014)
    assert RULES[Regime.PESCA].window is Window.FISCAL_3Y
    assert all(RULES[r].window is Window.ROLLING_3Y for r in (Regime.GENERAL, Regime.SIEG, Regime.AGRICOLA))


# --- Ventana móvil de 3 años, fecha a fecha (no ejercicios naturales) ------------------------------
@pytest.mark.parametrize(
    ("ref", "start"),
    [
        (date(2026, 10, 19), date(2023, 10, 20)),
        (date(2026, 1, 1), date(2023, 1, 2)),  # no es «2024-2026»: cruza tres años naturales distintos
        (date(2026, 12, 31), date(2024, 1, 1)),
        (date(2028, 2, 29), date(2025, 3, 1)),  # referencia 29-F: tres años antes no existe -> 28-F
        (date(2027, 2, 28), date(2024, 2, 29)),  # la ventana arranca justo en un 29-F
        (date(2027, 3, 1), date(2024, 3, 2)),
        (date(2024, 2, 29), date(2021, 3, 1)),
    ],
)
def test_rolling_window_is_date_to_date(ref, start):
    assert window_start(Window.ROLLING_3Y, ref) == start
    edge = three_years_before(ref)
    report = compute_headroom([aw(1, edge, 1_000), aw(2, edge + timedelta(days=1), 2_000)], ref, [A])
    assert report.usages[Regime.GENERAL].used_eur == 2_000  # el mismo día de hace 3 años ya no cuenta
    assert report.usages[Regime.GENERAL].window_end == ref


def test_window_length_is_exactly_three_years():
    for offset in range(0, 1500, 7):
        ref = date(2026, 1, 1) + timedelta(days=offset)
        days = (ref - window_start(Window.ROLLING_3Y, ref)).days + 1
        assert days in (1095, 1096)  # 1096 cuando la ventana contiene un 29 de febrero
        assert three_years_before(ref).year == ref.year - 3


def test_fiscal_window_for_fishing():
    assert window_start(Window.FISCAL_3Y, REF) == date(2024, 1, 1)


# --- Regímenes y acumulación ------------------------------------------------------------------------
def test_general_headroom_and_sieg_always_reported():
    report = compute_headroom([aw(1, date(2025, 1, 10), 100_000), aw(2, date(2026, 5, 1), 50_000)], REF, [A])
    assert report.general_headroom == 150_000
    assert set(report.usages) == {Regime.GENERAL, Regime.SIEG}
    assert report.usages[Regime.SIEG].headroom_eur == 600_000
    assert not report.exceeded


def test_agricultural_ceiling_and_cap_by_general():
    report = compute_headroom([aw(1, date(2025, 6, 1), 45_000, AGR)], REF, [A])
    assert report.usages[Regime.AGRICOLA].headroom_eur == 5_000
    capped = compute_headroom([aw(1, date(2025, 6, 1), 290_000), aw(2, date(2025, 7, 1), 1, AGR)], REF, [A])
    assert capped.usages[Regime.AGRICOLA].headroom_eur == pytest.approx(9_999)


def test_agricultural_overrun_is_exceeded_even_below_general():
    report = compute_headroom([aw(1, date(2025, 6, 1), 51_000, AGR)], REF, [A])
    assert report.exceeded and report.general_headroom == 249_000
    assert report.warnings[0].startswith("ATENCIÓN")


def test_fishing_fiscal_years_and_configurable_ceiling():
    awards = [aw(1, date(2023, 12, 31), 30_000, PES), aw(2, date(2024, 2, 1), 5_000, PES)]
    report = compute_headroom(awards, REF, [A])
    assert report.usages[Regime.PESCA].used_eur == 5_000
    assert report.usages[Regime.PESCA].headroom_eur == 35_000
    assert report.usages[Regime.GENERAL].used_eur == 35_000  # cuenta contra el general en ventana móvil
    base = compute_headroom(awards, REF, [A], fish_ceiling_eur=30_000)
    assert base.usages[Regime.PESCA].ceiling_eur == 30_000 and base.usages[Regime.PESCA].headroom_eur == 25_000


def test_sieg_prudent_joint_ceiling():
    report = compute_headroom([aw(1, date(2025, 1, 1), 100_000), aw(2, date(2025, 5, 1), 600_000, SIEG)], REF, [A])
    assert report.usages[Regime.GENERAL].used_eur == 100_000  # las SIEG no consumen el tope de 300.000
    assert report.general_headroom == 50_000  # pero general + SIEG <= 750.000 (criterio prudente)
    assert report.usages[Regime.SIEG].headroom_eur == 50_000
    assert any("Criterio prudente" in w for w in report.warnings)


def test_exceeded_ceiling_warns_first():
    report = compute_headroom([aw(1, date(2025, 1, 1), 310_000)], REF, [A])
    assert report.general_headroom == 0 and report.exceeded
    assert report.warnings[0].startswith("ATENCIÓN")


# --- «Única empresa» --------------------------------------------------------------------------------
def test_single_undertaking_sums_up_to_three_linked_companies():
    awards = [
        aw(1, date(2025, 1, 1), 100_000),
        aw(2, date(2025, 6, 1), 90_000, nif=B),
        aw(3, date(2026, 2, 1), 50_000, OLD, nif=C),
        aw(4, date(2026, 2, 1), 99_999, nif="Q2826000H"),  # no forma parte del grupo
    ]
    report = compute_headroom(awards, REF, [A, B, C])
    assert report.usages[Regime.GENERAL].used_eur == 240_000
    assert report.general_headroom == 60_000
    assert any("1407/2013" in w for w in report.warnings)
    assert not any("1 CIF" in w for w in report.warnings)
    single = compute_headroom(awards, REF, [A])
    assert single.general_headroom == 200_000 and any("1 CIF" in w for w in single.warnings)


def test_single_undertaking_notice_is_part_of_every_result():
    data = compute_headroom([], REF, [A]).to_dict()
    assert data["aviso_unica_empresa"] == SINGLE_UNDERTAKING_NOTICE
    assert "art. 2.2" in SINGLE_UNDERTAKING_NOTICE and "matriz o filiales" in SINGLE_UNDERTAKING_NOTICE


def test_dedupes_ignores_future_and_foreign_awards():
    awards = [
        aw(1, date(2025, 1, 1), 10_000),
        aw(1, date(2025, 1, 1), 10_000),
        aw(2, date(2026, 12, 1), 99_999),
        aw(3, date(2025, 1, 1), 50_000, nif=B),
    ]
    assert compute_headroom(awards, REF, [A]).usages[Regime.GENERAL].used_eur == 10_000


def test_unknown_regulation_counts_against_general():
    report = compute_headroom([aw(1, date(2025, 1, 1), 7_000, "")], REF, [A])
    assert report.usages[Regime.GENERAL].used_eur == 7_000
    assert any("no reconocido" in w for w in report.warnings)


@pytest.mark.parametrize(
    ("u", "color"), [(0, "verde"), (0.49, "verde"), (0.5, "ambar"), (0.84, "ambar"), (0.85, "rojo"), (1.2, "rojo")]
)
def test_semaforo_thresholds(u, color):
    assert semaforo(u) == color


def test_report_serialization():
    data = compute_headroom([aw(1, date(2025, 1, 1), 7_000)], REF, [A]).to_dict()
    assert data["margen_general_eur"] == 293_000
    assert (data["ventana_desde"], data["ventana_hasta"]) == ("2023-10-20", "2026-10-19")
    assert [r["regimen"] for r in data["regimenes"]] == ["general", "sieg"]
    assert data["semaforo"] == "verde" and data["concesiones"][0]["regimen"] == "general"
