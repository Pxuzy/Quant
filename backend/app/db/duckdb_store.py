"""DuckDB persistent store — 线程安全的持久连接，用于数值数据的批量导入和查询。

与 `data_loader.py` 不同，此模块面向后端 service/repository 层使用。
DuckDB 负责管理：daily_bars、factors_daily、financials_quarterly 三张持久表。
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

import duckdb

from backend.app.core.config import get_settings

_CONNECTIONS: dict[str, duckdb.DuckDBPyConnection] = {}
_WRITE_LOCK = Lock()


def get_duckdb(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    resolved_path = Path(db_path or get_settings().duckdb_path).expanduser().resolve()
    key = str(resolved_path)
    with _WRITE_LOCK:
        connection = _CONNECTIONS.get(key)
        if connection is None:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            connection = duckdb.connect(key)
            _CONNECTIONS[key] = connection
            _init_schema(connection)
        return connection


def _init_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Auto-create tables if not exist."""
    connection.execute("""
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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS factors_daily (
            symbol      VARCHAR,
            trade_date  DATE,
            factor_name VARCHAR,
            value       DOUBLE
        )
    """)
    connection.execute("""
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
    con = get_duckdb(db_path)
    with _WRITE_LOCK:
        key_columns = ("symbol", "exchange", "market", "trade_date", "adjust_type")
        value_columns = (
            "symbol", "exchange", "market", "trade_date", "open", "high", "low",
            "close", "pre_close", "volume", "amount", "adjust_factor", "adjust_type",
            "source", "ingested_at",
        )

        def row_values(row: dict) -> tuple:
            return tuple(row.get(column) for column in value_columns)

        deduped = {}
        for row in rows:
            key = tuple(
                row.get(column) if column != "adjust_type" else row.get(column) or "none"
                for column in key_columns
            )
            deduped[key] = row
        candidate_rows = list(deduped.values())
        con.execute("DROP TABLE IF EXISTS _tmp_bars")
        con.execute("CREATE TEMP TABLE _tmp_bars AS SELECT * FROM daily_bars WHERE 1=0")
        con.executemany(
            "INSERT INTO _tmp_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [row_values(row) for row in candidate_rows],
        )
        existing_rows = con.execute(
            """
            SELECT d.symbol, d.exchange, d.market, d.trade_date, d.adjust_type,
                   d.open, d.high, d.low, d.close, d.pre_close, d.volume, d.amount,
                   d.adjust_factor, d.source, d.ingested_at
            FROM daily_bars d
            JOIN _tmp_bars t
              ON d.symbol = t.symbol AND d.exchange = t.exchange
             AND d.market = t.market AND d.trade_date = t.trade_date
             AND d.adjust_type = t.adjust_type
            """
        ).fetchall()
        existing_by_key = {
            tuple(row[:5]): tuple(row[:4]) + tuple(row[5:13]) + (row[4],) + tuple(row[13:])
            for row in existing_rows
        }
        changed_rows = []
        for row in candidate_rows:
            key = tuple(
                row.get(column) if column != "adjust_type" else row.get(column) or "none"
                for column in key_columns
            )
            existing = existing_by_key.get(key)
            if existing is None or existing[:-1] != row_values(row)[:-1]:
                changed_rows.append(row)
        con.execute("DROP TABLE IF EXISTS _tmp_bars")
        if not changed_rows:
            return 0
        con.execute("CREATE TEMP TABLE _tmp_bars AS SELECT * FROM daily_bars WHERE 1=0")
        con.executemany(
            "INSERT INTO _tmp_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [row_values(row) for row in changed_rows],
        )
        try:
            con.execute("BEGIN TRANSACTION")
            con.execute(
                """
                DELETE FROM daily_bars d USING _tmp_bars t
                WHERE d.symbol = t.symbol AND d.exchange = t.exchange
                  AND d.market = t.market AND d.trade_date = t.trade_date
                  AND d.adjust_type = t.adjust_type
                """
            )
            con.execute("INSERT INTO daily_bars SELECT * FROM _tmp_bars")
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            finally:
                con.execute("DROP TABLE IF EXISTS _tmp_bars")
            raise
        con.execute("DROP TABLE IF EXISTS _tmp_bars")
        return len(changed_rows)


def close_duckdb() -> None:
    """优雅关闭。"""
    with _WRITE_LOCK:
        connections = list(_CONNECTIONS.values())
        _CONNECTIONS.clear()
    for connection in connections:
        try:
            connection.close()
        except Exception:
            pass
