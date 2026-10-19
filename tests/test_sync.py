from datetime import date, timedelta

from conftest import CIF_A, CIF_B, REF, FakeSource, conv_raw, minimis_raw

from radar_minimis.sync import date_windows, lookup_minimis, sync_convocatorias, sync_portfolio_awards


def test_date_windows_are_contiguous_newest_first():
    windows = date_windows(date(2026, 10, 1), date(2026, 10, 19), 7)
    assert windows[0] == (date(2026, 10, 13), date(2026, 10, 19))
    assert windows[-1][0] == date(2026, 10, 1)
    for (s1, _), (_, e2) in zip(windows, windows[1:], strict=False):
        assert e2 == s1 - timedelta(days=1)


def test_sync_is_idempotent_and_resumable(store):
    source = FakeSource(
        [
            conv_raw("900001", recepcion="2026-10-15"),
            conv_raw("900002", recepcion="2026-10-10"),
            conv_raw("900003", recepcion="2026-10-02"),
        ]
    )
    first = sync_convocatorias(source, store, desde=date(2026, 10, 1), hasta=REF, max_details=2)
    assert (first.nuevas, first.pendientes) == (2, 1)
    second = sync_convocatorias(source, store, desde=date(2026, 10, 1), hasta=REF)
    assert (second.nuevas, second.pendientes) == (1, 0)
    third = sync_convocatorias(source, store, desde=date(2026, 10, 1), hasta=REF)
    assert third.nuevas == 0 and source.calls["detail"] == 3
    assert store.stats()["convocatorias"] == 3


def test_sync_refreshes_recent_calls(store):
    source = FakeSource([conv_raw("900001", recepcion="2026-10-15")])
    sync_convocatorias(source, store, desde=date(2026, 10, 1), hasta=REF)
    again = sync_convocatorias(source, store, desde=date(2026, 10, 1), hasta=REF, refresh_since=date(2026, 10, 12))
    assert again.actualizadas == 1


def test_lookup_minimis_caches_and_requires_exact_nif(store):
    similar = CIF_A[:6] + "999"  # coincidencia parcial que devuelve la fuente falsa
    source = FakeSource(
        minimis=[minimis_raw(1, CIF_A, "2026-01-10", 5000), minimis_raw(2, similar, "2026-01-10", 7000)]
    )
    assert [a.award_id for a in lookup_minimis(source, store, CIF_A, ttl_hours=24)] == ["1"]
    lookup_minimis(source, store, CIF_A, ttl_hours=24)
    assert source.calls["nif"] == 1


def test_sync_portfolio_returns_only_new_awards(store):
    account_id, _ = store.upsert_account("asesoria@demo.test", "asesoria_50", "hash", "cus_1")
    store.add_to_portfolio(account_id, [(CIF_A, "Cliente A")])
    source = FakeSource(minimis=[minimis_raw(1, CIF_A, "2026-10-10", 5000), minimis_raw(2, CIF_B, "2026-10-11", 900)])
    first = sync_portfolio_awards(source, store, today=REF)
    assert [a.award_id for a in first] == ["1"]
    assert sync_portfolio_awards(source, store, today=REF) == []
