"""Encaje empresa <-> convocatoria: perfil inferido desde sus concesiones y reglas explicables."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .bdns.models import Convocatoria
from .minimis import Award

PYME = "PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA"
GENERIC_BENEFICIARY = "SIN INFORMACION ESPECIFICA"


@dataclass(frozen=True, slots=True)
class CompanyProfile:
    nif: str
    cnae_divisions: frozenset[str]
    nuts: str | None = None
    beneficiary_type: str = PYME


@dataclass(frozen=True, slots=True)
class Match:
    convocatoria: Convocatoria
    score: float
    motivos: tuple[str, ...]


def profile_from_awards(
    nif: str, awards: Iterable[Award], *, nuts: str | None = None, beneficiary_type: str = PYME
) -> CompanyProfile:
    """El CNAE de la empresa sale gratis de sus concesiones de minimis (`sectorActividad`)."""
    divisions = frozenset(
        a.sector_cnae[:2] for a in awards if a.nif == nif and a.sector_cnae and a.sector_cnae[:2].isdigit()
    )
    return CompanyProfile(nif, divisions, (nuts or "").upper() or None, beneficiary_type)


def _divisions(conv: Convocatoria) -> set[str]:
    return {code.replace(".", "")[:2] for code, _ in conv.sectores if code[:2].isdigit()}


def evaluate(conv: Convocatoria, profile: CompanyProfile, today: date) -> Match | None:
    if conv.estado(today) not in ("abierta", "sin_plazo"):
        return None
    score, motivos = 0.0, []

    tipos = {t.upper() for t in conv.tipos_beneficiario}
    if tipos:
        if profile.beneficiary_type.upper() not in tipos and GENERIC_BENEFICIARY not in tipos:
            return None
        score += 1.0
        motivos.append("Admite tu tipo de beneficiario")

    divisions = _divisions(conv)
    if divisions and profile.cnae_divisions:
        if not divisions & profile.cnae_divisions:
            return None
        score += 2.0
        motivos.append("Coincide con tu actividad (CNAE)")
    elif not divisions:
        score += 0.5
        motivos.append("Sin restricción de sector")
    else:
        motivos.append("Sector no verificable: tu CIF no tiene concesiones con CNAE")

    # "XXX"/"XXXX" (fuera de Europa / todo el mundo) no restringe dónde está la empresa.
    nuts_codes = [code for code, _ in conv.regiones if code and not code.startswith("X")]
    if nuts_codes and profile.nuts:
        related = [c for c in nuts_codes if profile.nuts.startswith(c) or c.startswith(profile.nuts)]
        if not related:
            return None
        score += max(len(c) for c in related) / 5
        motivos.append("Ámbito territorial compatible")

    dias = conv.dias_para_cierre(today)
    if dias is not None and dias <= 15:
        score += 0.5
        motivos.append(f"Cierra en {dias} días")
    if conv.is_minimis:
        motivos.append("Sujeta a minimis: comprueba tu margen")
    return Match(conv, round(score, 2), tuple(motivos))


def match(convocatorias: Iterable[Convocatoria], profile: CompanyProfile, today: date, limit: int = 20) -> list[Match]:
    found = [m for m in (evaluate(c, profile, today) for c in convocatorias) if m is not None]
    found.sort(key=lambda m: (-m.score, m.convocatoria.fecha_fin_solicitud or date.max))
    return found[:limit]
