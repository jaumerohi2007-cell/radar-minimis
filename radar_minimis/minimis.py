"""Margen de minimis de una «única empresa»: el núcleo del producto.

Base normativa verificada el 19-10-2026 sobre los textos del DOUE (copia del BOE) y el BOE:
- Reg. (UE) 2023/2831, art. 3.2: 300.000 EUR «durante cualquier período de tres años». Considerando 11: el período
  «debe evaluarse de forma continua» con «los tres años previos». Art. 3.3: la ayuda cuenta desde que se confiere
  el derecho legal, no desde el pago. Art. 5.2: se acumula con las de los Reg. 1408/2013 y 717/2014 hasta 300.000 EUR.
  Art. 5.1: se acumula con las SIEG del Reg. 2023/2832 sin tope conjunto expreso (ver CRITERIO_ACUMULACION).
- Reg. (UE) 2023/2832, art. 3.2: 750.000 EUR (SIEG) durante cualquier período de tres años.
- Reg. (UE) 1408/2013 en la redacción del Reg. (UE) 2024/3118, art. 3.2: 50.000 EUR en cualquier período de tres años.
- Reg. (UE) 717/2014 en la redacción del Reg. (UE) 2023/2391: 30.000 EUR (art. 3.2) o 40.000 EUR si el Estado lo
  decide y tiene registro central (art. 3.2 bis); España lo aplica (RD 1139/2024, art. 3.2). Tres ejercicios fiscales.

Convención de fechas: la ventana móvil termina en la fecha de referencia (fecha prevista de concesión; por defecto,
hoy en Madrid) y empieza el día siguiente al mismo día de tres años antes: fecha a fecha, equivalente a
`referencia - relativedelta(years=3)` con comparación estricta. Un 29 de febrero retrocede al 28.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum


class Regime(StrEnum):
    GENERAL = "general"
    SIEG = "sieg"
    AGRICOLA = "agricola"
    PESCA = "pesca"
    DESCONOCIDO = "desconocido"


class Window(StrEnum):
    ROLLING_3Y = "tres_anos_moviles"
    FISCAL_3Y = "ejercicio_en_curso_y_dos_anteriores"


@dataclass(frozen=True, slots=True)
class RegimeRule:
    regime: Regime
    ceiling_eur: float
    window: Window
    legal_basis: str


PESCA_BASE_CEILING_EUR = 30_000.0  # art. 3.2 Reg. 717/2014, si el Estado no aplica el art. 3.2 bis

RULES: dict[Regime, RegimeRule] = {
    Regime.GENERAL: RegimeRule(Regime.GENERAL, 300_000.0, Window.ROLLING_3Y, "Reg. (UE) 2023/2831, art. 3.2"),
    Regime.SIEG: RegimeRule(Regime.SIEG, 750_000.0, Window.ROLLING_3Y, "Reg. (UE) 2023/2832, art. 3.2"),
    Regime.AGRICOLA: RegimeRule(
        Regime.AGRICOLA, 50_000.0, Window.ROLLING_3Y, "Reg. (UE) 1408/2013, art. 3.2 (redacción del Reg. 2024/3118)"
    ),
    Regime.PESCA: RegimeRule(
        Regime.PESCA,
        40_000.0,
        Window.FISCAL_3Y,
        "Reg. (UE) 717/2014, art. 3.2 bis (Reg. 2023/2391) y RD 1139/2024, art. 3.2",
    ),
}

# Regímenes que suman contra el tope general de 300.000 EUR (art. 5.2 del Reg. 2023/2831).
_COUNTS_AGAINST_GENERAL = (Regime.GENERAL, Regime.AGRICOLA, Regime.PESCA, Regime.DESCONOCIDO)

SINGLE_UNDERTAKING_NOTICE = (
    "«Única empresa» (art. 2.2 del Reg. (UE) 2023/2831): el tope se comparte entre todas las empresas que tengan "
    "entre sí al menos uno de estos vínculos: a) una posee la mayoría de los derechos de voto de los socios de otra; "
    "b) una puede nombrar o revocar a la mayoría del órgano de administración, dirección o supervisión de otra; "
    "c) una puede ejercer una influencia dominante sobre otra por contrato o por sus estatutos; d) una, socia de "
    "otra, controla por sí sola la mayoría de los derechos de voto por acuerdo con otros socios. También cuentan "
    "estos vínculos a través de otras empresas. Si tu empresa tiene matriz o filiales, suma sus CIF: el margen de "
    "un solo CIF puede ser mayor que el real."
)
CRITERIO_ACUMULACION = (
    "Criterio prudente: el art. 5.1 del Reg. (UE) 2023/2831 permite acumular ayudas generales y SIEG sin fijar un "
    "tope conjunto expreso; la calculadora limita la suma general + SIEG a 750.000 € para no sobrestimar el margen."
)
BASE_WARNINGS = (
    "Solo incluye ayudas registradas en la BDNS; las concesiones recientes pueden tardar en aparecer.",
    "Informe orientativo, no constituye asesoramiento jurídico.",
)

WARN_SINGLE_CIF = "Calculado para 1 CIF: si hay empresas vinculadas, añádelas (ver «única empresa»)."
WARN_EXCEEDED = "ATENCIÓN: las ayudas registradas superan al menos uno de los topes aplicables."
WARN_UNKNOWN = "{n} concesión(es) con reglamento no reconocido se han sumado al tope general."
WARN_LEGACY = "Incluye ayudas del Reg. (UE) 1407/2013 concedidas dentro del período de tres años."
WARN_PESCA = "Pesca: se computan el ejercicio en curso y los dos anteriores (ejercicio = año natural)."

# Semáforo por utilización del tope más exigente (usado / tope).
SEMAFORO_AMBAR = 0.50
SEMAFORO_ROJO = 0.85


def classify_regulation(text: str | None) -> Regime:
    """Clasifica el campo `reglamento` de la BDNS (p. ej. 'REG (UE) 2023/2831 de minimis, General')."""
    t = (text or "").lower()
    if "1408/2013" in t or "agrícola" in t or "agricola" in t:
        return Regime.AGRICOLA
    if "717/2014" in t or "pesca" in t:
        return Regime.PESCA
    if "2023/2832" in t or "360/2012" in t or "sieg" in t or "interés económico general" in t:
        return Regime.SIEG
    if "2023/2831" in t or "1407/2013" in t or "general" in t:
        return Regime.GENERAL
    return Regime.DESCONOCIDO


@dataclass(frozen=True, slots=True)
class Award:
    """Una concesión de minimis tal y como se usa en el cálculo."""

    award_id: str
    nif: str
    beneficiary: str
    granted_on: date
    amount_eur: float  # ayuda equivalente bruta (campo `ayudaEquivalente`)
    regulation: str
    grantor: str = ""
    call_code: str | None = None
    sector_cnae: str | None = None

    @property
    def regime(self) -> Regime:
        return classify_regulation(self.regulation)

    @property
    def is_legacy_general(self) -> bool:
        return "1407/2013" in self.regulation


def three_years_before(reference: date) -> date:
    """El mismo día tres años antes (equivale a `reference - relativedelta(years=3)`)."""
    try:
        return reference.replace(year=reference.year - 3)
    except ValueError:  # 29 de febrero -> 28 de febrero
        return reference.replace(year=reference.year - 3, day=28)


def window_start(rule_window: Window, reference: date) -> date:
    """Primer día incluido en la ventana que termina en `reference` (también incluida)."""
    if rule_window is Window.FISCAL_3Y:
        return date(reference.year - 2, 1, 1)
    return three_years_before(reference) + timedelta(days=1)


def semaforo(utilization: float) -> str:
    if utilization >= SEMAFORO_ROJO:
        return "rojo"
    if utilization >= SEMAFORO_AMBAR:
        return "ambar"
    return "verde"


@dataclass(frozen=True, slots=True)
class RegimeUsage:
    regime: Regime
    ceiling_eur: float
    used_eur: float
    headroom_eur: float
    window_start: date
    window_end: date
    awards: tuple[Award, ...]
    legal_basis: str

    @property
    def utilization(self) -> float:
        return self.used_eur / self.ceiling_eur if self.ceiling_eur else 0.0

    def to_dict(self) -> dict:
        return {
            "regimen": self.regime.value,
            "tope_eur": self.ceiling_eur,
            "usado_eur": round(self.used_eur, 2),
            "margen_eur": round(self.headroom_eur, 2),
            "ventana_desde": self.window_start.isoformat(),
            "ventana_hasta": self.window_end.isoformat(),
            "base_legal": self.legal_basis,
            "n_concesiones": len(self.awards),
        }


@dataclass(frozen=True, slots=True)
class HeadroomReport:
    reference_date: date
    nifs: tuple[str, ...]
    usages: dict[Regime, RegimeUsage]
    awards_in_window: tuple[Award, ...]
    ignored_outside_window: int
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def general_headroom(self) -> float:
        return self.usages[Regime.GENERAL].headroom_eur

    @property
    def exceeded(self) -> bool:
        return any(u.used_eur > u.ceiling_eur for u in self.usages.values())

    @property
    def utilization(self) -> float:
        """Utilización del tope más exigente (0 = sin ayudas; >1 = superado)."""
        return max(u.utilization for u in self.usages.values())

    def to_dict(self) -> dict:
        general = self.usages[Regime.GENERAL]
        return {
            "fecha_referencia": self.reference_date.isoformat(),
            "ventana_desde": general.window_start.isoformat(),
            "ventana_hasta": general.window_end.isoformat(),
            "cifs": list(self.nifs),
            "margen_general_eur": round(self.general_headroom, 2),
            "tope_superado": self.exceeded,
            "utilizacion": round(self.utilization, 4),
            "semaforo": semaforo(self.utilization),
            "regimenes": [u.to_dict() for u in self.usages.values()],
            "concesiones": [
                {
                    "id": a.award_id,
                    "cif": a.nif,
                    "beneficiario": a.beneficiary,
                    "fecha_concesion": a.granted_on.isoformat(),
                    "importe_equivalente_eur": a.amount_eur,
                    "reglamento": a.regulation,
                    "regimen": a.regime.value,
                    "concedente": a.grantor,
                    "codigo_bdns": a.call_code,
                }
                for a in self.awards_in_window
            ],
            "concesiones_fuera_de_ventana": self.ignored_outside_window,
            "aviso_unica_empresa": SINGLE_UNDERTAKING_NOTICE,
            "criterio_acumulacion": CRITERIO_ACUMULACION,
            "advertencias": list(self.warnings),
        }


def compute_headroom(
    awards: Iterable[Award], reference: date, nifs: Iterable[str], *, fish_ceiling_eur: float | None = None
) -> HeadroomReport:
    """Calcula el margen disponible por régimen para la única empresa formada por `nifs`."""
    nif_set = tuple(dict.fromkeys(nifs))
    unique: dict[str, Award] = {}
    for a in awards:
        if a.nif in nif_set and a.granted_on <= reference:
            unique.setdefault(a.award_id, a)
    all_awards = sorted(unique.values(), key=lambda a: (a.granted_on, a.award_id), reverse=True)

    rolling_from = window_start(Window.ROLLING_3Y, reference)
    fiscal_from = window_start(Window.FISCAL_3Y, reference)
    rolling = [a for a in all_awards if a.granted_on >= rolling_from]
    by_regime: dict[Regime, list[Award]] = {r: [a for a in rolling if a.regime is r] for r in Regime}
    fiscal_pesca = [a for a in all_awards if a.regime is Regime.PESCA and a.granted_on >= fiscal_from]

    general_awards = [a for a in rolling if a.regime in _COUNTS_AGAINST_GENERAL]
    general_used = sum(a.amount_eur for a in general_awards)
    sieg_used = sum(a.amount_eur for a in by_regime[Regime.SIEG])
    general_rule, sieg_rule = RULES[Regime.GENERAL], RULES[Regime.SIEG]
    general_headroom = max(
        0.0,
        min(general_rule.ceiling_eur - general_used, sieg_rule.ceiling_eur - general_used - sieg_used),
    )

    def usage(rule: RegimeRule, used: float, headroom: float, pool: list[Award], ceiling: float | None = None):
        return RegimeUsage(
            rule.regime,
            ceiling if ceiling is not None else rule.ceiling_eur,
            used,
            headroom,
            window_start(rule.window, reference),
            reference,
            tuple(pool),
            rule.legal_basis,
        )

    usages: dict[Regime, RegimeUsage] = {
        Regime.GENERAL: usage(general_rule, general_used, general_headroom, general_awards),
        Regime.SIEG: usage(
            sieg_rule,
            sieg_used + general_used,
            max(0.0, sieg_rule.ceiling_eur - sieg_used - general_used),
            by_regime[Regime.SIEG],
        ),
    }
    if by_regime[Regime.AGRICOLA]:
        rule = RULES[Regime.AGRICOLA]
        used = sum(a.amount_eur for a in by_regime[Regime.AGRICOLA])
        usages[Regime.AGRICOLA] = usage(
            rule, used, max(0.0, min(rule.ceiling_eur - used, general_headroom)), by_regime[Regime.AGRICOLA]
        )
    if fiscal_pesca:
        rule = RULES[Regime.PESCA]
        ceiling = fish_ceiling_eur if fish_ceiling_eur is not None else rule.ceiling_eur
        used = sum(a.amount_eur for a in fiscal_pesca)
        usages[Regime.PESCA] = usage(rule, used, max(0.0, min(ceiling - used, general_headroom)), fiscal_pesca, ceiling)

    warnings = list(BASE_WARNINGS)
    if len(nif_set) == 1:
        warnings.insert(0, WARN_SINGLE_CIF)
    if any(u.used_eur > u.ceiling_eur for u in usages.values()):
        warnings.insert(0, WARN_EXCEEDED)
    if by_regime[Regime.DESCONOCIDO]:
        warnings.append(WARN_UNKNOWN.format(n=len(by_regime[Regime.DESCONOCIDO])))
    if any(a.is_legacy_general for a in rolling):
        warnings.append(WARN_LEGACY)
    if Regime.PESCA in usages:
        warnings.append(WARN_PESCA)
    if sieg_used:
        warnings.append(CRITERIO_ACUMULACION)

    shown_ids = {a.award_id for a in rolling} | {a.award_id for a in fiscal_pesca}
    shown = tuple(a for a in all_awards if a.award_id in shown_ids)
    return HeadroomReport(
        reference_date=reference,
        nifs=nif_set,
        usages=usages,
        awards_in_window=shown,
        ignored_outside_window=len(all_awards) - len(shown),
        warnings=tuple(warnings),
    )
