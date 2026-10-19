"""Acceso a la API pública del Sistema Nacional de Publicidad de Subvenciones (BDNS)."""

from .client import BDNSClient, BDNSError
from .models import Convocatoria, award_from_api

__all__ = ["BDNSClient", "BDNSError", "Convocatoria", "award_from_api"]
