from __future__ import annotations

from datetime import date

from apps.api.adapters.base import NormalizedDailyBar
from apps.api.repositories.daily_bars import DailyBarRepository


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
