"""API HTTP (FastAPI): margen de minimis, informe, lista de espera, métricas, cartera y webhook de Stripe.

Con BILLING_MODE=validation (por defecto) las funciones de pago se sustituyen por una «puerta falsa»: la API
responde 402 con el origen del clic y la web abre el alta en la lista de espera. El código de Stripe sigue
intacto y solo se monta con BILLING_MODE=stripe.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from datetime import date, timedelta

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import ATTRIBUTION, DISCLAIMER, __version__
from ..bdns.client import BDNSClient, BDNSError
from ..billing import (
    DEFAULT_PLAN,
    PLANS,
    LogMailer,
    Mailer,
    ResendMailer,
    SignatureError,
    handle_event,
    hash_api_key,
    verify_stripe_signature,
)
from ..config import Settings, today_madrid
from ..leads import (
    CONSENTIMIENTO_VERSION,
    EARLY_ACCESS_COPY,
    EARLY_ACCESS_TITLE,
    EVENTOS_CLIENTE,
    LeadError,
    validate_lead,
)
from ..matching import match, profile_from_awards
from ..minimis import compute_headroom
from ..privacy import NifKind, classify, normalize
from ..store import Store
from ..sync import BDNSSource, lookup_minimis

MAX_GROUP_CIFS_PRO = 20
FRESH_REPORT_MAX_AGE = timedelta(minutes=10)


class RateLimiter:
    """Ventana deslizante de 60 s más cupo diario por clave. En memoria: pensado para un único proceso."""

    def __init__(self, per_minute: int, per_day: int, clock: Callable[[], float] = time.time) -> None:
        self.per_minute, self.per_day, self.clock = per_minute, per_day, clock
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._daily: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, daily: bool = True) -> None:
        now = self.clock()
        day = int(now // 86_400)
        with self._lock:
            recent = self._recent[key]
            while recent and now - recent[0] > 60:
                recent.popleft()
            if len(recent) >= self.per_minute:
                raise HTTPException(429, "Demasiadas consultas seguidas. Espera un minuto.")
            if daily:
                stored_day, count = self._daily.get(key, (day, 0))
                count = 0 if stored_day != day else count
                if count >= self.per_day:
                    raise HTTPException(
                        429,
                        f"Has alcanzado el límite gratuito de {self.per_day} consultas diarias. "
                        "Con Asesorías Pro las consultas son ilimitadas.",
                    )
                self._daily[key] = (day, count + 1)
            recent.append(now)
            if len(self._recent) > 50_000:  # poda de claves inactivas
                for k in [k for k, q in self._recent.items() if not q]:
                    del self._recent[k]


def validate_nifs(values: list[str]) -> list[str]:
    """Solo personas jurídicas con dígito de control válido (regla de privacidad del producto)."""
    nifs: list[str] = []
    for value in values:
        nif = normalize(value)
        kind = classify(nif)
        if kind is NifKind.NATURAL_PERSON:
            raise HTTPException(
                422,
                f"{nif} corresponde a una persona física: por protección de datos solo "
                "se admiten CIF de personas jurídicas.",
            )
        if kind is NifKind.INVALID:
            raise HTTPException(422, f"{nif or '(vacío)'} no es un CIF válido: revisa el dígito de control.")
        nifs.append(nif)
    return list(dict.fromkeys(nifs))


def pro_required(settings: Settings, origen: str) -> HTTPException:
    """402 con la información que necesita la web para abrir la lista de espera o el pago."""
    if settings.validation_mode:
        detail = {
            "codigo": "acceso_anticipado",
            "origen": origen,
            "titulo": EARLY_ACCESS_TITLE,
            "mensaje": EARLY_ACCESS_COPY,
        }
    else:
        detail = {
            "codigo": "requiere_plan",
            "origen": origen,
            "checkout_url": settings.stripe_payment_link or None,
            "mensaje": "Función del plan Asesorías Pro.",
        }
    return HTTPException(402, detail)


class CarteraIn(BaseModel):
    cifs: list[str] = Field(min_length=1, max_length=500)
    alias: dict[str, str] = Field(default_factory=dict)


def create_app(
    settings: Settings | None = None,
    *,
    source: BDNSSource | None = None,
    mailer: Mailer | None = None,
    today: Callable[[], date] = today_madrid,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if not settings.validation_mode and not settings.stripe_webhook_secret:
        raise ValueError("BILLING_MODE=stripe requiere RM_STRIPE_WEBHOOK_SECRET")
    if source is None:
        source = BDNSClient(
            settings.bdns_base_url,
            user_agent=settings.user_agent,
            rate_per_sec=settings.bdns_rate_per_sec,
            timeout_s=settings.bdns_timeout_s,
        )
    if mailer is None:
        mailer = ResendMailer(settings.resend_api_key, settings.mail_from) if settings.resend_api_key else LogMailer()
    limiter = limiter or RateLimiter(per_minute=20, per_day=settings.free_lookups_per_day)
    form_limiter = RateLimiter(per_minute=10, per_day=30)

    app = FastAPI(
        title="Radar Minimis API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    def get_store() -> Iterator[Store]:
        store = Store(settings.db_path)
        try:
            yield store
        finally:
            store.close()

    def client_key(request: Request) -> str:
        # Detrás de Cloudflare/Caddy la IP real llega en cabecera. Solo se usa en memoria para el cupo.
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() or (request.client.host if request.client else "anon")

    def optional_account(x_api_key: str | None = Header(default=None), store: Store = Depends(get_store)):
        if not x_api_key or settings.validation_mode:
            return None
        account = store.account_by_key_hash(hash_api_key(x_api_key))
        if account is None:
            raise HTTPException(401, "API key no válida o inactiva.")
        return account

    def require_account(x_api_key: str | None = Header(default=None), store: Store = Depends(get_store)):
        if settings.validation_mode:
            raise pro_required(settings, "cartera_lote")
        account = optional_account(x_api_key, store)
        if account is None:
            raise HTTPException(401, "Falta la cabecera X-API-Key.")
        return account

    def throttle(request: Request, account) -> None:
        if account is None:
            limiter.check(client_key(request))
        else:
            limiter.check(f"cuenta:{account['id']}", daily=False)

    def awards_for(store: Store, nifs: list[str], max_age: timedelta | None = None):
        try:
            return [
                a
                for nif in nifs
                for a in lookup_minimis(source, store, nif, ttl_hours=settings.minimis_cache_ttl_h, max_age=max_age)
            ]
        except BDNSError as exc:
            raise HTTPException(503, "La BDNS no responde ahora mismo. Inténtalo en unos minutos.") from exc

    @app.get("/api/health")
    def health(store: Store = Depends(get_store)) -> dict:
        return {
            "ok": True,
            "version": __version__,
            "modo": settings.billing_mode,
            "datos_actualizados": store.get_meta("last_sync_convocatorias"),
        }

    @app.get("/api/minimis/{cif}")
    def minimis(
        cif: str,
        request: Request,
        vinculadas: str = "",
        fecha: date | None = None,
        fresco: bool = False,
        store: Store = Depends(get_store),
        account=Depends(optional_account),
    ) -> dict:
        nifs = validate_nifs([cif, *(v for v in vinculadas.split(",") if v.strip())])
        if account is None and len(nifs) > settings.free_group_max_cifs:
            raise pro_required(settings, "grupo_societario")
        if len(nifs) > MAX_GROUP_CIFS_PRO:
            raise HTTPException(422, f"Máximo {MAX_GROUP_CIFS_PRO} CIF por grupo.")
        throttle(request, account)
        awards = awards_for(store, nifs, FRESH_REPORT_MAX_AGE if fresco else None)
        report = compute_headroom(awards, fecha or today(), nifs, fish_ceiling_eur=settings.fish_ceiling_eur)
        store.incr_metric("calculo_minimis", today().isoformat())
        return {
            **report.to_dict(),
            "fecha_referencia_indicada": fecha is not None,
            "consultas_bdns": [
                {"cif": n, "consultado_en": store.lookup_time(n), "n_concesiones": sum(a.nif == n for a in awards)}
                for n in nifs
            ],
            "beneficiarios": {a.nif: a.beneficiary for a in awards if a.beneficiary},
            "atribucion": ATTRIBUTION,
            "aviso": DISCLAIMER,
            "modo": settings.billing_mode,
        }

    @app.get("/api/encaje/{cif}")
    def encaje(
        cif: str,
        request: Request,
        provincia: str | None = Query(None, pattern=r"^ES[0-9A-Z]{0,3}$"),
        limite: int = Query(10, ge=1, le=50),
        store: Store = Depends(get_store),
        account=Depends(optional_account),
    ) -> dict:
        nifs = validate_nifs([cif])
        throttle(request, account)
        profile = profile_from_awards(nifs[0], awards_for(store, nifs), nuts=provincia)
        found = match(store.open_convocatorias(today()), profile, today(), limit=limite)
        return {
            "cif": profile.nif,
            "cnae_inferido": sorted(profile.cnae_divisions),
            "provincia": profile.nuts,
            "convocatorias": [
                {
                    "codigo_bdns": m.convocatoria.codigo_bdns,
                    "titulo": m.convocatoria.titulo,
                    "organo": m.convocatoria.organo_nivel3 or m.convocatoria.organo_nivel2,
                    "cierre": m.convocatoria.fecha_fin_solicitud.isoformat()
                    if m.convocatoria.fecha_fin_solicitud
                    else None,
                    "presupuesto_eur": m.convocatoria.presupuesto_total,
                    "puntuacion": m.score,
                    "motivos": list(m.motivos),
                    "url_oficial": m.convocatoria.url_oficial,
                }
                for m in found
            ],
            "atribucion": ATTRIBUTION,
        }

    @app.post("/api/waitlist", status_code=201)
    def waitlist(request: Request, payload: dict = Body(...), store: Store = Depends(get_store)) -> dict:
        form_limiter.check(f"form:{client_key(request)}")
        try:
            lead = validate_lead(payload)
        except LeadError as exc:
            raise HTTPException(422, str(exc)) from exc
        if lead is not None:  # los bots (campo trampa) reciben la misma respuesta y no se guardan
            store.add_lead(
                lead.email, lead.num_cifs_estimados, lead.cif_consultado, lead.origen_clic, CONSENTIMIENTO_VERSION
            )
            store.incr_metric(f"lead_{lead.origen_clic}", today().isoformat())
        return {"ok": True, "mensaje": "¡Gracias! Te escribiremos por orden de solicitud. No se te cobrará nada ahora."}

    @app.post("/api/evento", status_code=204)
    def evento(request: Request, payload: dict = Body(...), store: Store = Depends(get_store)) -> Response:
        form_limiter.check(f"evento:{client_key(request)}", daily=False)
        tipo = payload.get("tipo")
        if tipo not in EVENTOS_CLIENTE:
            raise HTTPException(422, "Evento no reconocido.")
        store.incr_metric(tipo, today().isoformat())
        return Response(status_code=204)

    @app.get("/api/cartera")
    def cartera(fecha: date | None = None, account=Depends(require_account), store: Store = Depends(get_store)):
        items = store.portfolio(account["id"])
        nifs = [r["nif"] for r in items]
        awards = store.awards_for(nifs)
        ref = fecha or today()
        empresas = []
        for row in items:
            report = compute_headroom(
                [a for a in awards if a.nif == row["nif"]],
                ref,
                [row["nif"]],
                fish_ceiling_eur=settings.fish_ceiling_eur,
            )
            empresas.append(
                {
                    "cif": row["nif"],
                    "alias": row["alias"],
                    "margen_general_eur": round(report.general_headroom, 2),
                    "tope_superado": report.exceeded,
                    "semaforo": report.to_dict()["semaforo"],
                    "n_concesiones": len(report.awards_in_window),
                }
            )
        plan = PLANS.get(account["plan"], PLANS[DEFAULT_PLAN])
        return {"plan": plan.code, "max_cifs": plan.max_nifs, "fecha_referencia": ref.isoformat(), "empresas": empresas}

    @app.post("/api/cartera")
    def cartera_add(body: CarteraIn, account=Depends(require_account), store: Store = Depends(get_store)) -> dict:
        nifs = validate_nifs(body.cifs)
        current = {r["nif"] for r in store.portfolio(account["id"])}
        plan = PLANS.get(account["plan"], PLANS[DEFAULT_PLAN])
        total = current | set(nifs)
        if len(total) > plan.max_nifs:
            raise HTTPException(409, f"Tu plan admite {plan.max_nifs} CIF; tendrías {len(total)}.")
        store.add_to_portfolio(account["id"], [(n, body.alias.get(n)) for n in nifs])
        for nif in set(nifs) - current:  # precarga; si la BDNS falla, la sync diaria lo completará
            try:
                lookup_minimis(source, store, nif, ttl_hours=settings.minimis_cache_ttl_h)
            except BDNSError:
                break
        return {"anadidos": len(set(nifs) - current), "total": len(total)}

    if not settings.validation_mode:

        @app.post("/webhooks/stripe")
        async def stripe_webhook(request: Request) -> dict:
            payload = await request.body()
            try:
                event = verify_stripe_signature(
                    payload, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret
                )
            except SignatureError as exc:
                raise HTTPException(400, str(exc)) from exc

            def process() -> str:
                store = Store(settings.db_path)
                try:
                    return handle_event(event, store, mailer)
                finally:
                    store.close()

            return {"recibido": True, "resultado": await run_in_threadpool(process)}

    if settings.site_dir.is_dir():  # vista previa local del sitio estático
        app.mount("/", StaticFiles(directory=settings.site_dir, html=True), name="site")
    return app
