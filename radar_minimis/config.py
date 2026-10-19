"""Configuración desde variables de entorno, con un `.env` opcional junto a `src/`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
BILLING_MODES = ("validation", "stripe")


def today_madrid() -> date:
    """El «día de la consulta» es el de España, aunque el servidor funcione en UTC."""
    return datetime.now(MADRID).date()


def _load_dotenv(path: Path) -> None:
    """Carga líneas KEY=VALUE sin dependencias externas; nunca pisa variables ya definidas."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    site_dir: Path
    site_url: str
    api_url: str
    contact_email: str
    bdns_base_url: str
    bdns_rate_per_sec: float
    bdns_timeout_s: float
    minimis_cache_ttl_h: int
    site_max_pages: int
    site_window_days: int
    free_lookups_per_day: int
    stripe_webhook_secret: str
    resend_api_key: str
    mail_from: str
    allowed_origins: tuple[str, ...]
    billing_mode: str = "validation"
    free_group_max_cifs: int = 2
    pro_linked_slots: int = 3
    stripe_payment_link: str = ""
    leads_api_url: str = ""
    fish_ceiling_eur: float = 40_000.0
    legal_owner: str = "[Titular del sitio: nombre o razón social y NIF]"
    privacy_email: str = ""
    google_site_verification: str = ""

    def __post_init__(self) -> None:
        if self.billing_mode not in BILLING_MODES:
            raise ValueError(f"BILLING_MODE debe ser uno de {BILLING_MODES}, no {self.billing_mode!r}")
        if self.free_group_max_cifs < 1:
            raise ValueError("RM_FREE_GROUP_MAX_CIFS debe ser >= 1")

    @property
    def validation_mode(self) -> bool:
        return self.billing_mode == "validation"

    @property
    def user_agent(self) -> str:
        return f"RadarMinimis/0.2 (+{self.site_url}; {self.contact_email})"

    @classmethod
    def from_env(cls, dotenv: Path | None = BASE_DIR / ".env") -> Settings:
        if dotenv is not None:
            _load_dotenv(dotenv)
        env = os.environ.get
        site_url = env("RM_SITE_URL", "http://localhost:8000").rstrip("/")
        api_url = env("RM_API_URL", site_url).rstrip("/")
        origins = tuple(o.strip() for o in env("RM_ALLOWED_ORIGINS", site_url).split(",") if o.strip())
        contact = env("RM_CONTACT_EMAIL", "contacto@example.com")
        return cls(
            db_path=Path(env("RM_DB_PATH", str(BASE_DIR / "data" / "radar.db"))),
            site_dir=Path(env("RM_SITE_DIR", str(BASE_DIR / "site_dist"))),
            site_url=site_url,
            api_url=api_url,
            contact_email=contact,
            bdns_base_url=env("RM_BDNS_BASE_URL", "https://www.infosubvenciones.es/bdnstrans/api"),
            bdns_rate_per_sec=float(env("RM_BDNS_RATE_PER_SEC", "2")),
            bdns_timeout_s=float(env("RM_BDNS_TIMEOUT_S", "60")),
            minimis_cache_ttl_h=int(env("RM_MINIMIS_CACHE_TTL_H", "24")),
            site_max_pages=int(env("RM_SITE_MAX_PAGES", "15000")),
            site_window_days=int(env("RM_SITE_WINDOW_DAYS", "120")),
            free_lookups_per_day=int(env("RM_FREE_LOOKUPS_PER_DAY", "10")),
            stripe_webhook_secret=env("RM_STRIPE_WEBHOOK_SECRET", ""),
            resend_api_key=env("RM_RESEND_API_KEY", ""),
            mail_from=env("RM_MAIL_FROM", "Radar Minimis <alertas@example.com>"),
            allowed_origins=origins,
            billing_mode=env("BILLING_MODE", "validation").strip().lower(),
            free_group_max_cifs=int(env("RM_FREE_GROUP_MAX_CIFS", "2")),
            pro_linked_slots=int(env("RM_PRO_LINKED_SLOTS", "3")),
            stripe_payment_link=env("RM_STRIPE_PAYMENT_LINK", ""),
            leads_api_url=env("RM_LEADS_API_URL", "").rstrip("/"),
            fish_ceiling_eur=float(env("RM_TOPE_PESCA_EUR", "40000")),
            legal_owner=env("RM_LEGAL_OWNER", "[Titular del sitio: nombre o razón social y NIF]"),
            privacy_email=env("RM_PRIVACY_EMAIL", contact),
            google_site_verification=env("RM_GOOGLE_SITE_VERIFICATION", "").strip(),
        )
