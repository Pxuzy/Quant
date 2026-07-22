from __future__ import annotations

from datetime import date

from backend.app.adapters.base import NormalizedDailyBar
from backend.app.repositories.daily_bars import DailyBarRepository


def test_daily_bars_repository_uses_duckdb_for_filtered_queries(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    repo.write_many(
        [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=1665.0,
                high=1680.0,
                low=1660.0,
                close=1675.0,
                pre_close=None,
                volume=1000.0,
                amount=1675000.0,
                adjust_factor=1.0,
                source="akshare",
            ),
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 2),
                open=1678.0,
                high=1690.0,
                low=1670.0,
                close=1688.0,
                pre_close=1675.0,
                volume=1100.0,
                amount=1856800.0,
                adjust_factor=1.0,
                source="akshare",
            ),
            NormalizedDailyBar(
                symbol="000001",
                exchange="SZSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 2),
                open=10.0,
                high=10.5,
                low=9.9,
                close=10.2,
                pre_close=10.0,
                volume=2000.0,
                amount=20400.0,
                adjust_factor=1.0,
                source="baostock",
            ),
        ]
    )

    def fail_pyarrow_fallback():
        raise AssertionError("DuckDB query should not fall back to full PyArrow scan.")

    monkeypatch.setattr(repo, "_read_partition_rows", fail_pyarrow_fallback)

    rows, total = repo.list_daily_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        page=2,
        page_size=1,
    )

    assert total == 2
    assert [row["trade_date"] for row in rows] == [date(2026, 6, 2)]
    assert rows[0]["source"] == "akshare"
    assert rows[0]["adjust_type"] == "none"
    assert rows[0]["ingested_at"] is not None
    assert repo.count(market="A_SHARE") == 3
    assert repo.latest_trade_date(market="A_SHARE") == date(2026, 6, 2)


def test_daily_bars_repository_reads_symbol_rows_with_adjust_types_via_duckdb(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    repo.write_many(
        [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=1665.0,
                high=1680.0,
                low=1660.0,
                close=1675.0,
                pre_close=None,
                volume=1000.0,
                amount=1675000.0,
                adjust_factor=1.0,
                source="akshare",
                adjust_type="none",
            ),
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=1665.0,
                high=1681.0,
                low=1661.0,
                close=1676.0,
                pre_close=None,
                volume=1001.0,
                amount=1676000.0,
                adjust_factor=1.0,
                source="akshare",
                adjust_type="qfq",
            ),
            NormalizedDailyBar(
                symbol="000001",
                exchange="SZSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=10.0,
                high=10.5,
                low=9.9,
                close=10.2,
                pre_close=None,
                volume=2000.0,
                amount=20400.0,
                adjust_factor=1.0,
                source="baostock",
            ),
        ]
    )

    def fail_pyarrow_fallback():
        raise AssertionError("DuckDB symbol query should not fall back to full PyArrow scan.")

    monkeypatch.setattr(repo, "_read_partition_rows", fail_pyarrow_fallback)

    rows = repo.symbol_daily_bars(symbol="600519", market="A_SHARE")

    assert len(rows) == 2
    assert [row["adjust_type"] for row in rows] == ["none", "qfq"]
    assert {row["symbol"] for row in rows} == {"600519"}


def test_list_daily_bars_reuses_symbol_fast_path_for_single_stock(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    calls: list[tuple[str, str]] = []

    def symbol_rows(*, symbol: str, market: str):
        calls.append((symbol, market))
        return [
            {"symbol": symbol, "market": market, "trade_date": date(2026, 6, 1), "adjust_type": "none"},
            {"symbol": symbol, "market": market, "trade_date": date(2026, 6, 2), "adjust_type": "none"},
        ]

    def fail_duckdb_list(*args, **kwargs):
        raise AssertionError("single-stock list should not run the generic count + page query")

    monkeypatch.setattr(repo, "symbol_daily_bars", symbol_rows)
    monkeypatch.setattr(repo, "_try_duckdb", fail_duckdb_list)

    rows, total = repo.list_daily_bars(
        symbol="600519",
        market="A_SHARE",
        page=1,
        page_size=1,
        sort_order="desc",
    )

    assert calls == [("600519", "A_SHARE")]
    assert total == 2
    assert [row["trade_date"] for row in rows] == [date(2026, 6, 2)]


def test_daily_bars_repository_isolates_parquet_by_lake_root_and_reports_idempotent_writes(tmp_path, monkeypatch):
    first_repo = DailyBarRepository(lake_root=tmp_path / "first-lake")
    second_repo = DailyBarRepository(lake_root=tmp_path / "second-lake")
    record = NormalizedDailyBar(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        trade_date=date(2026, 6, 1),
        open=1665.0,
        high=1680.0,
        low=1660.0,
        close=1675.0,
        pre_close=None,
        volume=1000.0,
        amount=1675000.0,
        adjust_factor=1.0,
        source="fixture",
    )

    assert first_repo.write_many([record]) == 1
    assert first_repo.write_many([record]) == 0
    assert first_repo.read_all()[0]["close"] == 1675.0
    assert second_repo.read_all() == []
    assert first_repo.count(market="A_SHARE") == 1
    assert second_repo.count(market="A_SHARE") == 0


def test_daily_bars_repository_keeps_last_duplicate_and_reads_parquet_truth(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    first = NormalizedDailyBar(
        symbol="600519", exchange="SSE", market="A_SHARE", trade_date=date(2026, 6, 1),
        open=1665.0, high=1680.0, low=1660.0, close=1675.0, pre_close=None,
        volume=1000.0, amount=1675000.0, adjust_factor=1.0, source="fixture",
    )
    replacement = NormalizedDailyBar(
        symbol="600519", exchange="SSE", market="A_SHARE", trade_date=date(2026, 6, 1),
        open=1665.0, high=1690.0, low=1660.0, close=1685.0, pre_close=None,
        volume=1000.0, amount=1685000.0, adjust_factor=1.0, source="fixture",
        ingested_at=first.ingested_at,
    )

    assert repo.write_many([first, replacement]) == 1

    rows, total = repo.list_daily_bars(symbol="600519", market="A_SHARE")

    assert total == 1
    assert rows[0]["close"] == 1685.0


def test_daily_bars_repository_propagates_parquet_write_failure(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    record = NormalizedDailyBar(
        symbol="600519", exchange="SSE", market="A_SHARE", trade_date=date(2026, 6, 1),
        open=1665.0, high=1680.0, low=1660.0, close=1675.0, pre_close=None,
        volume=1000.0, amount=1675000.0, adjust_factor=1.0, source="fixture",
    )
    monkeypatch.setattr(
        "backend.app.repositories.daily_bars.pq.write_table",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    try:
        repo.write_many([record])
    except OSError as exc:
        assert str(exc) == "disk full"
    else:
        raise AssertionError("Parquet failures must not be reported as successful writes")


def test_daily_bars_repository_replaces_existing_parquet_row_without_persistent_duckdb(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    first = NormalizedDailyBar(
        symbol="600519", exchange="SSE", market="A_SHARE", trade_date=date(2026, 6, 1),
        open=1665.0, high=1680.0, low=1660.0, close=1675.0, pre_close=None,
        volume=1000.0, amount=1675000.0, adjust_factor=1.0, source="fixture",
    )
    replacement = NormalizedDailyBar(
        symbol="600519", exchange="SSE", market="A_SHARE", trade_date=date(2026, 6, 1),
        open=1665.0, high=1690.0, low=1660.0, close=1685.0, pre_close=None,
        volume=1000.0, amount=1685000.0, adjust_factor=1.0, source="fixture",
        ingested_at=first.ingested_at,
    )
    assert repo.write_many([first]) == 1
    assert repo.write_many([replacement]) == 1
    assert repo.read_all()[0]["close"] == 1685.0
