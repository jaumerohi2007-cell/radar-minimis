#!/usr/bin/env python3
"""Motor de datos y tracción de Radar Minimis.

Extrae convocatorias y concesiones de minimis de la API pública de la BDNS, alimenta la base
SQLite, genera el sitio pSEO estático y sirve la API.

    uv run python data_engine.py sync                      # incremental (o carga inicial si la base está vacía)
    uv run python data_engine.py sync --days 30 --max-details 3000
    uv run python data_engine.py sync-cartera             # concesiones nuevas de los CIF vigilados + alertas
    uv run python data_engine.py build-site                # genera site_dist/ para Cloudflare Pages
    uv run python data_engine.py minimis B12345674 [A11111119 ...] [--fecha 2026-10-19]
    uv run python data_engine.py encaje B12345674 [--provincia ES417]
    uv run python data_engine.py stats
    uv run python data_engine.py reindex                   # re-parsea lo guardado (sin red)
    uv run python data_engine.py leads [--export leads_validacion.json] [--d1 radar-minimis-db] [--borrar EMAIL]
    uv run python data_engine.py serve [--host 127.0.0.1] [--port 8000]
    uv run python data_engine.py cuentas                  # licencias de pago en D1 (--rotar ID: clave nueva)
    uv run python data_engine.py daily                     # sync + sync-cartera + build-site (cron)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from radar_minimis import leads as leadsmod
from radar_minimis.alerts import notify_new_awards
from radar_minimis.bdns.client import BDNSClient
from radar_minimis.bdns.models import Convocatoria
from radar_minimis.billing import LogMailer, ResendMailer
from radar_minimis.config import Settings, today_madrid
from radar_minimis.matching import match, profile_from_awards
from radar_minimis.minimis import compute_headroom
from radar_minimis.privacy import NifKind, classify, normalize
from radar_minimis.site import SiteBuilder
from radar_minimis.site.builder import format_eur
from radar_minimis.store import Store
from radar_minimis.sync import lookup_minimis, sync_convocatorias, sync_portfolio_awards, sync_range

log = logging.getLogger("data_engine")


def _client(settings: Settings) -> BDNSClient:
    return BDNSClient(
        settings.bdns_base_url,
        user_agent=settings.user_agent,
        rate_per_sec=settings.bdns_rate_per_sec,
        timeout_s=settings.bdns_timeout_s,
    )


def _date(value: str) -> date:
    return date.fromisoformat(value)


def cmd_sync(args, settings: Settings) -> int:
    today = today_madrid()
    with Store(settings.db_path) as store, _client(settings) as client:
        if args.desde:
            desde, hasta = args.desde, args.hasta or today
        elif args.days:
            desde, hasta = today - timedelta(days=args.days - 1), today
        else:
            desde, hasta = sync_range(store, today, backfill_days=args.backfill_days)
            if (hasta - desde).days + 1 > 3:
                log.info("Carga inicial o pendientes: %s..%s (%d días)", desde, hasta, (hasta - desde).days + 1)
        report = sync_convocatorias(
            client,
            store,
            desde=desde,
            hasta=hasta,
            refresh_since=today - timedelta(days=args.refresh_days),
            max_details=args.max_details,
        )
        print(f"Convocatorias {report}")
        return 1 if report.errores and not (report.nuevas or report.actualizadas) else 0


def cmd_sync_cartera(args, settings: Settings) -> int:
    if settings.validation_mode:
        print("Cartera: BILLING_MODE=validation, vigilancia y alertas desactivadas (se miden en la lista de espera)")
        return 0
    mailer = ResendMailer(settings.resend_api_key, settings.mail_from) if settings.resend_api_key else LogMailer()
    with Store(settings.db_path) as store, _client(settings) as client:
        new = sync_portfolio_awards(client, store, today=today_madrid(), days=args.days)
        sent = notify_new_awards(store, mailer, new)
    print(f"Cartera: {len(new)} concesiones nuevas, {sent} emails de alerta")
    return 0


def cmd_build_site(args, settings: Settings) -> int:
    with Store(settings.db_path) as store:
        report = SiteBuilder(settings, store).build()
    print(f"Sitio generado: {report}")
    return 0


def _valid_legal_entities(values: list[str]) -> list[str] | None:
    nifs = [normalize(v) for v in values]
    for nif in nifs:
        kind = classify(nif)
        if kind is not NifKind.LEGAL_ENTITY:
            print(
                f"{nif}: "
                + (
                    "persona física (no admitida por protección de datos)"
                    if kind is NifKind.NATURAL_PERSON
                    else "CIF no válido"
                ),
                file=sys.stderr,
            )
            return None
    return nifs


def cmd_minimis(args, settings: Settings) -> int:
    nifs = _valid_legal_entities(args.cif)
    if nifs is None:
        return 2
    with Store(settings.db_path) as store, _client(settings) as client:
        awards = [a for nif in nifs for a in lookup_minimis(client, store, nif, ttl_hours=settings.minimis_cache_ttl_h)]
    report = compute_headroom(awards, args.fecha or today_madrid(), nifs, fish_ceiling_eur=settings.fish_ceiling_eur)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(f"\nMargen de minimis a {report.reference_date:%d/%m/%Y} para {', '.join(report.nifs)}")
    print(f"{'Régimen':<12}{'Usado':>14}{'Tope':>14}{'Margen':>14}  Desde")
    for u in report.usages.values():
        print(
            f"{u.regime.value:<12}{format_eur(u.used_eur):>14}{format_eur(u.ceiling_eur):>14}"
            f"{format_eur(u.headroom_eur):>14}  {u.window_start:%d/%m/%Y}"
        )
    print(f"\nConcesiones en el periodo: {len(report.awards_in_window)}")
    for a in report.awards_in_window:
        print(f"  {a.granted_on:%d/%m/%Y}  {format_eur(a.amount_eur):>12}  {a.regime.value:<10} {a.grantor[:60]}")
    print("\nAdvertencias:")
    for w in report.warnings:
        print(f"  - {w}")
    return 0


def cmd_encaje(args, settings: Settings) -> int:
    nifs = _valid_legal_entities([args.cif])
    if nifs is None:
        return 2
    today = today_madrid()
    with Store(settings.db_path) as store, _client(settings) as client:
        awards = lookup_minimis(client, store, nifs[0], ttl_hours=settings.minimis_cache_ttl_h)
        profile = profile_from_awards(nifs[0], awards, nuts=args.provincia)
        found = match(store.open_convocatorias(today), profile, today, limit=args.limite)
    print(
        f"Perfil {profile.nif}: CNAE {sorted(profile.cnae_divisions) or 'desconocido'}, "
        f"ámbito {profile.nuts or 'cualquiera'}"
    )
    for m in found:
        c = m.convocatoria
        print(f"  [{m.score:>4}] {c.codigo_bdns}  cierra {c.fecha_fin_solicitud or '—'}  {c.titulo[:80]}")
        print(f"         {'; '.join(m.motivos)}")
    if not found:
        print("  Sin convocatorias abiertas que encajen (amplía la base con `sync --days 30`).")
    return 0


def cmd_reindex(args, settings: Settings) -> int:
    """Vuelve a parsear el JSON guardado (tras mejorar el parser) sin llamar a la BDNS."""
    with Store(settings.db_path) as store:
        raws = list(store.iter_raw_convocatorias())
        with store.transaction():
            for raw in raws:
                store.upsert_convocatoria(Convocatoria.from_api(raw), raw)
    print(f"Reindexadas {len(raws)} convocatorias")
    return 0


def cmd_leads(args, settings: Settings) -> int:
    """Métricas de la validación (lista de espera + embudo), exportación y derecho de supresión."""
    since = (today_madrid() - timedelta(days=args.dias - 1)).isoformat()
    try:
        if args.d1:
            if args.borrar:
                leadsmod.d1_delete_leads(args.d1, args.borrar)
                print(f"Borrados los envíos de {args.borrar} en D1:{args.d1}")
                return 0
            rows, metrics, source = leadsmod.d1_leads(args.d1), leadsmod.d1_metrics(args.d1, since), f"D1:{args.d1}"
        else:
            with Store(settings.db_path) as store:
                if args.borrar:
                    print(f"Borrados {store.delete_leads(args.borrar)} envíos de {args.borrar}")
                    return 0
                rows, metrics, source = store.leads(), store.metrics(since), f"SQLite:{settings.db_path}"
    except (leadsmod.D1Error, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(leadsmod.format_summary(leadsmod.summarize(rows, metrics), source=source, days=args.dias))
    if args.export:
        leadsmod.export(rows, args.export)
        print(f"Exportados {len(rows)} envíos a {args.export}")
    return 0


def cmd_cuentas(args, settings: Settings) -> int:
    """Licencias del plan Asesorías Pro en D1 y reemisión manual de la clave de acceso."""
    try:
        if args.rotar:
            key = leadsmod.d1_rotate_key(args.d1, args.rotar)
            print(f"Clave nueva de la cuenta {args.rotar} (se muestra una sola vez; la anterior ya no vale):\n{key}")
            return 0
        rows = leadsmod.d1_accounts(args.d1)
    except (leadsmod.D1Error, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    activas = sum(1 for r in rows if r.get("activa"))
    print(f"Cuentas en D1:{args.d1}: {len(rows)} ({activas} activas)")
    for r in rows:
        print(f"  #{r['id']}  {r['email']}  {r['estado']}  {r['cifs']} CIF  alta {str(r['creada_en'])[:10]}")
    return 0


def cmd_cloudflare_constants(args, settings: Settings) -> int:
    from radar_minimis.cloudflare_export import write_constants

    print(f"Generado {write_constants()}")
    return 0


def cmd_stats(args, settings: Settings) -> int:
    with Store(settings.db_path) as store:
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args, settings: Settings) -> int:
    import uvicorn

    from radar_minimis.api import create_app

    uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=True)
    return 0


def cmd_daily(args, settings: Settings) -> int:
    sync_args = argparse.Namespace(
        desde=None,
        hasta=None,
        days=None,
        backfill_days=args.backfill_days,
        refresh_days=7,
        max_details=args.max_details,
    )
    status = cmd_sync(sync_args, settings)
    cmd_sync_cartera(argparse.Namespace(days=45), settings)
    cmd_build_site(args, settings)
    return status


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Motor de datos de Radar Minimis (BDNS)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sync", help="sincroniza convocatorias desde la BDNS")
    s.add_argument("--days", type=int, help="últimos N días (por defecto 3, ampliado hasta cubrir lo pendiente)")
    s.add_argument("--desde", type=_date)
    s.add_argument("--hasta", type=_date)
    s.add_argument("--backfill-days", type=int, default=30)
    s.add_argument("--refresh-days", type=int, default=7, help="vuelve a descargar las registradas en estos días")
    s.add_argument("--max-details", type=int, help="tope de detalles por ejecución (reanudable)")
    s.set_defaults(func=cmd_sync)

    c = sub.add_parser("sync-cartera", help="concesiones nuevas de CIF vigilados + alertas")
    c.add_argument("--days", type=int, default=45)
    c.set_defaults(func=cmd_sync_cartera)

    sub.add_parser("build-site", help="genera el sitio pSEO en site_dist/").set_defaults(func=cmd_build_site)

    m = sub.add_parser("minimis", help="margen de minimis de uno o varios CIF (única empresa)")
    m.add_argument("cif", nargs="+")
    m.add_argument("--fecha", type=_date)
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_minimis)

    e = sub.add_parser("encaje", help="convocatorias abiertas que encajan con un CIF")
    e.add_argument("cif")
    e.add_argument("--provincia", help="código NUTS, p. ej. ES417 (Soria) o ES30 (Madrid)")
    e.add_argument("--limite", type=int, default=10)
    e.set_defaults(func=cmd_encaje)

    sub.add_parser("stats", help="estado de la base de datos").set_defaults(func=cmd_stats)
    sub.add_parser("reindex", help="re-parsea el JSON guardado sin red").set_defaults(func=cmd_reindex)

    sub.add_parser("cloudflare-constants", help="regenera cloudflare/constants.js desde Python").set_defaults(
        func=cmd_cloudflare_constants
    )

    ld = sub.add_parser("leads", help="métricas de validación, exportación y supresión de leads")
    ld.add_argument("--export", type=Path, help="fichero .json (p. ej. leads_validacion.json) o .csv")
    ld.add_argument("--d1", metavar="BASE", help="leer de Cloudflare D1 remoto (requiere `wrangler login`)")
    ld.add_argument("--borrar", metavar="EMAIL", help="borra todos los envíos de ese email (RGPD)")
    ld.add_argument("--dias", type=int, default=30, help="ventana de métricas del embudo")
    ld.set_defaults(func=cmd_leads)

    ct = sub.add_parser("cuentas", help="licencias de pago en Cloudflare D1 y reemisión de claves")
    ct.add_argument("--d1", metavar="BASE", default="radar-minimis-db", help="base D1 remota (`wrangler login`)")
    ct.add_argument("--rotar", type=int, metavar="ID", help="emite una clave nueva para la cuenta ID")
    ct.set_defaults(func=cmd_cuentas)

    v = sub.add_parser("serve", help="sirve la API (y el sitio generado) en local")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.set_defaults(func=cmd_serve)

    d = sub.add_parser("daily", help="tarea diaria completa (cron / GitHub Actions)")
    d.add_argument("--backfill-days", type=int, default=30)
    d.add_argument("--max-details", type=int, default=4000)
    d.set_defaults(func=cmd_daily)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return args.func(args, Settings.from_env())


if __name__ == "__main__":
    sys.exit(main())
