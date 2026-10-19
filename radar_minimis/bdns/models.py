"""Modelos tipados de la API BDNS con parseo tolerante (los campos pueden venir nulos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..minimis import Award
from ..privacy import NifKind, classify, split_beneficiary

OFFICIAL_CALL_URL = "https://www.infosubvenciones.es/bdnstrans/GE/es/convocatoria/{codigo}"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _descriptions(items: list[dict] | None) -> tuple[str, ...]:
    return tuple((i.get("descripcion") or "").strip() for i in (items or []) if i.get("descripcion"))


def _text(value) -> str | None:
    """Algunos campos llegan como texto y otros como objeto {"descripcion": ...} (p. ej. `reglamento`)."""
    if isinstance(value, dict):
        value = value.get("descripcion")
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _split_code(text: str) -> tuple[str, str]:
    """'ES417 - Soria' -> ('ES417', 'Soria')."""
    code, sep, name = text.partition(" - ")
    return (code.strip(), name.strip()) if sep else ("", text.strip())


@dataclass(frozen=True, slots=True)
class Convocatoria:
    codigo_bdns: str
    titulo: str
    organo_nivel1: str
    organo_nivel2: str
    organo_nivel3: str
    fecha_recepcion: date | None
    fecha_inicio_solicitud: date | None
    fecha_fin_solicitud: date | None
    texto_inicio: str | None
    texto_fin: str | None
    presupuesto_total: float | None
    tipo_convocatoria: str | None
    instrumentos: tuple[str, ...]
    tipos_beneficiario: tuple[str, ...]
    sectores: tuple[tuple[str, str], ...]  # (código CNAE, descripción)
    regiones: tuple[tuple[str, str], ...]  # (código NUTS, nombre)
    finalidad: str | None
    bases_reguladoras: str | None
    url_bases: str | None
    sede_electronica: str | None
    reglamento: str | None
    ayuda_estado: str | None
    mrr: bool
    documentos: tuple[tuple[int, str], ...]

    @classmethod
    def from_api(cls, d: dict) -> Convocatoria:
        organo = d.get("organo") or {}
        return cls(
            codigo_bdns=str(d.get("codigoBDNS") or d.get("numeroConvocatoria") or "").strip(),
            titulo=(d.get("descripcion") or "").strip(),
            organo_nivel1=(organo.get("nivel1") or d.get("nivel1") or "").strip(),
            organo_nivel2=(organo.get("nivel2") or d.get("nivel2") or "").strip(),
            organo_nivel3=(organo.get("nivel3") or d.get("nivel3") or "").strip(),
            fecha_recepcion=parse_date(d.get("fechaRecepcion")),
            fecha_inicio_solicitud=parse_date(d.get("fechaInicioSolicitud")),
            fecha_fin_solicitud=parse_date(d.get("fechaFinSolicitud")),
            texto_inicio=d.get("textInicio"),
            texto_fin=d.get("textFin"),
            presupuesto_total=float(d["presupuestoTotal"]) if d.get("presupuestoTotal") is not None else None,
            tipo_convocatoria=d.get("tipoConvocatoria"),
            instrumentos=_descriptions(d.get("instrumentos")),
            tipos_beneficiario=_descriptions(d.get("tiposBeneficiarios")),
            sectores=tuple(
                ((s.get("codigo") or "").strip(), (s.get("descripcion") or "").strip())
                for s in (d.get("sectores") or [])
            ),
            regiones=tuple(_split_code(r) for r in _descriptions(d.get("regiones"))),
            finalidad=d.get("descripcionFinalidad"),
            bases_reguladoras=d.get("descripcionBasesReguladoras"),
            url_bases=d.get("urlBasesReguladoras"),
            sede_electronica=d.get("sedeElectronica"),
            reglamento=_text(d.get("reglamento")),
            ayuda_estado=_text(d.get("ayudaEstado")),
            mrr=bool(d.get("mrr")),
            documentos=tuple(
                (int(doc["id"]), (doc.get("descripcion") or doc.get("nombreFic") or "Documento").strip())
                for doc in (d.get("documentos") or [])
                if doc.get("id") is not None
            ),
        )

    @property
    def is_minimis(self) -> bool:
        haystack = " ".join(filter(None, (self.reglamento, self.ayuda_estado, self.bases_reguladoras, self.titulo)))
        return "minimis" in haystack.lower()

    @property
    def url_oficial(self) -> str:
        return OFFICIAL_CALL_URL.format(codigo=self.codigo_bdns)

    def estado(self, today: date) -> str:
        if self.fecha_fin_solicitud and self.fecha_fin_solicitud < today:
            return "cerrada"
        if self.fecha_inicio_solicitud and self.fecha_inicio_solicitud > today:
            return "proxima"
        if self.fecha_fin_solicitud:
            return "abierta"
        return "sin_plazo"

    def dias_para_cierre(self, today: date) -> int | None:
        if self.fecha_fin_solicitud is None or self.fecha_fin_solicitud < today:
            return None
        return (self.fecha_fin_solicitud - today).days


def award_from_api(d: dict) -> Award | None:
    """Convierte una fila de `minimis/busqueda`. Devuelve None si no es una persona jurídica válida."""
    nif, name = split_beneficiary(d.get("beneficiario") or "")
    if nif is None or classify(nif) is not NifKind.LEGAL_ENTITY:
        return None
    granted = parse_date(d.get("fechaConcesion"))
    amount = d.get("ayudaEquivalente")
    if granted is None or amount is None:
        return None
    sector = (d.get("sectorActividad") or "").split(" - ", 1)[0].strip() or None
    return Award(
        award_id=str(d.get("idConcesion") or d.get("codigoConcesion")),
        nif=nif,
        beneficiary=name,
        granted_on=granted,
        amount_eur=float(amount),
        regulation=(d.get("reglamento") or "").strip(),
        grantor=(d.get("convocante") or "").strip(),
        call_code=str(d["numeroConvocatoria"]) if d.get("numeroConvocatoria") else None,
        sector_cnae=sector,
    )
