from __future__ import annotations

from datetime import date

import duckdb
import pytest

from backend.app.adapters.base import NormalizedDailyBar
from backend.app.core.config import get_settings
from backend.app.db.duckdb_store import close_duckdb
from backend.app.repositories.daily_bars import DailyBarArchiveError, DailyBarRepository


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

    monkeypatch.setattr(repo, "_read_all", fail_pyarrow_fallback)

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

    monkeypatch.setattr(repo, "_read_all", fail_pyarrow_fallback)

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


def test_daily_bar_repositories_isolate_duckdb_by_lake_root(tmp_path, monkeypatch):
    first_lake = tmp_path / "first" / "lake"
    second_lake = tmp_path / "second" / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(first_lake))
    get_settings.cache_clear()
    first_repo = DailyBarRepository()

    first_repo.write_many(
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
                source="fixture",
            )
        ]
    )

    assert first_repo.symbol_daily_bars(symbol="600519", market="A_SHARE")

    monkeypatch.setenv("DATA_LAKE_DIR", str(second_lake))
    get_settings.cache_clear()
    second_repo = DailyBarRepository()
    second_repo.write_many(
        [
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
                source="fixture",
            )
        ]
    )

    assert [row["trade_date"] for row in second_repo.symbol_daily_bars(symbol="600519", market="A_SHARE")] == [
        date(2026, 6, 2)
    ]


def test_daily_bar_write_many_reports_only_new_rows(tmp_path):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    row = NormalizedDailyBar(
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

    assert repo.write_many([row]) == 1
    assert repo.write_many([row]) == 0
    assert repo.count(market="A_SHARE") == 1


def test_daily_bar_archive_failure_is_visible_after_duckdb_write(tmp_path, monkeypatch):
    repo = DailyBarRepository(lake_root=tmp_path / "lake", duckdb_path=tmp_path / "bars.duckdb")
    row = NormalizedDailyBar(
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

    def fail_parquet_write(*args, **kwargs):
        raise OSError("archive unavailable")

    monkeypatch.setattr("backend.app.repositories.daily_bars.pq.write_table", fail_parquet_write)
    with pytest.raises(DailyBarArchiveError) as exc_info:
        repo.write_many([row])

    assert exc_info.value.records_written == 1
    close_duckdb()
    with duckdb.connect(str(tmp_path / "bars.duckdb"), read_only=True) as connection:
        assert connection.execute("select count(*) from daily_bars").fetchone()[0] == 1
