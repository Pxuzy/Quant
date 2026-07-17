"""DuckDB persistent store — 线程安全的持久连接，用于数值数据的批量导入和查询。

与 `data_loader.py` 不同，此模块面向后端 service/repository 层使用。
DuckDB 负责管理：daily_bars、factors_daily、financials_quarterly 三张持久表。
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import duckdb

from backend.app.core.config import get_settings


_CONN: duckdb.DuckDBPyConnection | None = None
_DB_PATH: str = ""
_WRITE_LOCK = Lock()


def get_duckdb(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """获取线程安全的持久 DuckDB 连接（单例）。"""
    global _CONN, _DB_PATH

    requested_path = str(db_path or get_settings().duckdb_path)
    if _CONN is not None and _DB_PATH == requested_path:
        return _CONN

    if _CONN is not None:
        try:
            _CONN.close()
        except Exception:
            pass

    path = Path(requested_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _CONN = duckdb.connect(str(path))
    _DB_PATH = requested_path
    _init_schema()
    return _CONN


def _init_schema() -> None:
    """Auto-create tables if not exist."""
    if _CONN is None:
        return
    _CONN.execute("""
        CREATE TABLE IF NOT EXISTS daily_bars (
            symbol          VARCHAR,
            exchange        VARCHAR,
            market          VARCHAR,
            trade_date      DATE,
            open            DOUBLE,
            high            DOUBLE,
            low             DOUBLE,
            close           DOUBLE,
            pre_close       DOUBLE,
            volume          DOUBLE,
            amount          DOUBLE,
            adjust_factor   DOUBLE,
            adjust_type     VARCHAR,
            source          VARCHAR,
            ingested_at     TIMESTAMP
        )
    """)
    _CONN.execute("""
        CREATE TABLE IF NOT EXISTS factors_daily (
            symbol      VARCHAR,
            trade_date  DATE,
            factor_name VARCHAR,
            value       DOUBLE
        )
    """)
    _CONN.execute("""
        CREATE TABLE IF NOT EXISTS financials_quarterly (
            symbol      VARCHAR,
            report_date DATE,
            metric_name VARCHAR,
            value       DOUBLE
        )
    """)


def write_daily_bars(rows: list[dict], *, db_path: str | Path | None = None) -> int:
    """将行情数据写入 DuckDB 持久表（幂等去重 + 线程安全），批量 INSERT VALUES 加速。"""
    if not rows:
        return 0
    con = get_duckdb(db_path=db_path)
    with _WRITE_LOCK:
        # Build bulk VALUES clause using parameterized approach via temp table
        chunk_size = 5000
        written_total = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            con.execute("CREATE TEMP TABLE IF NOT EXISTS _tmp_bars AS SELECT * FROM daily_bars WHERE 1=0")
            con.executemany(
                "INSERT INTO _tmp_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(
                    r.get("symbol"),
                    r.get("exchange"),
                    r.get("market"),
                    r.get("trade_date"),
                    r.get("open"),
                    r.get("high"),
                    r.get("low"),
                    r.get("close"),
                    r.get("pre_close"),
                    r.get("volume"),
                    r.get("amount"),
                    r.get("adjust_factor"),
                    r.get("adjust_type") or "none",
                    r.get("source"),
                    r.get("ingested_at"),
                ) for r in chunk],
            )
            # Dedup insert: only rows not already in daily_bars
            result = con.execute("""
                INSERT INTO daily_bars
                SELECT DISTINCT * FROM _tmp_bars
                WHERE NOT EXISTS (
                    SELECT 1 FROM daily_bars d
                    WHERE d.symbol = _tmp_bars.symbol
                      AND d.exchange = _tmp_bars.exchange
                      AND d.market = _tmp_bars.market
                      AND d.trade_date = _tmp_bars.trade_date
                      AND d.adjust_type = _tmp_bars.adjust_type
                )
            """)
            written_total += result.fetchone()[0]
            con.execute("DROP TABLE IF EXISTS _tmp_bars")

        return written_total


def close_duckdb() -> None:
    """优雅关闭。"""
    global _CONN, _DB_PATH
    if _CONN is not None:
        try:
            _CONN.close()
        except Exception:
            pass
        _CONN = None
        _DB_PATH = ""
