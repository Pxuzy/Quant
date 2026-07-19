from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

try:
    import duckdb
except ModuleNotFoundError:  # pragma: no cover - exercised only in partial installs
    duckdb = None

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.adapters.base import NormalizedDailyBar, normalize_daily_bar_adjust_type
from backend.app.core.config import get_settings


DAILY_BAR_COLUMNS = [
    "symbol",
    "exchange",
    "market",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "adjust_factor",
    "adjust_type",
    "source",
    "ingested_at",
]


class DailyBarArchiveError(RuntimeError):
    """DuckDB accepted rows, but immutable Parquet archive could not be finalized."""

    def __init__(self, message: str, *, records_written: int) -> None:
        super().__init__(message)
        self.records_written = records_written


def _duckdb_connect_with_timeout() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection."""
    return duckdb.connect()


class DailyBarRepository:
    def __init__(
        self,
        *,
        lake_root: str | Path | None = None,
        dataset_dir: str | Path | None = None,
        duckdb_path: str | Path | None = None,
    ) -> None:
        settings = get_settings()
        self.lake_root = Path(lake_root or settings.data_lake_dir)
        self.dataset_dir = Path(dataset_dir) if dataset_dir is not None else self.lake_root / "silver" / "daily_bars"
        if duckdb_path is not None:
            self.duckdb_path = Path(duckdb_path)
        elif os.getenv("DUCKDB_PATH"):
            self.duckdb_path = Path(settings.duckdb_path)
        else:
            self.duckdb_path = self.lake_root.parent / "quant.duckdb"

    def write_many(self, records: list[NormalizedDailyBar]) -> int:
        if not records:
            return 0

        rows = [_normalize_row(asdict(record)) for record in records]

        # Primary write: DuckDB persistent store (幂等去重)
        from backend.app.db.duckdb_store import write_daily_bars
        written = write_daily_bars(rows, db_path=self.duckdb_path)

        # Archive: Parquet 湖存储 (best-effort, 非阻塞)
        try:
            rows_by_partition: dict[tuple[str, date], list[dict]] = {}
            for row in rows:
                rows_by_partition.setdefault((row["market"], row["trade_date"]), []).append(row)

            for (market, trade_date), group in rows_by_partition.items():
                partition_dir = self.dataset_dir / f"market={market}" / f"trade_date={trade_date.isoformat()}"
                partition_dir.mkdir(parents=True, exist_ok=True)
                file_path = partition_dir / "part-000.parquet"

                if file_path.exists():
                    group = [_normalize_row(row) for row in _read_parquet_file(file_path)] + group

                deduped = {
                    (row["symbol"], row["exchange"], row["market"], row["trade_date"], row["adjust_type"]): row
                    for row in group
                }
                sorted_rows = sorted(deduped.values(), key=lambda row: (row["symbol"], row["exchange"], row["adjust_type"]))
                pq.write_table(pa.Table.from_pylist(sorted_rows, schema=DAILY_BAR_ARROW_SCHEMA), file_path)
        except Exception as exc:
            raise DailyBarArchiveError(
                "Daily bar Parquet archive failed after canonical write.",
                records_written=written,
            ) from exc

        return written

    def list_daily_bars(
        self,
        *,
        symbol: str | None = None,
        market: str | None = None,
        adjust_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        page_size: int = 200,
        sort_order: str = "asc",
    ) -> tuple[list[dict], int]:
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type) if adjust_type is not None else None
        if symbol and market:
            rows = self.symbol_daily_bars(symbol=symbol.strip(), market=market)
            if adjust_type_code is not None:
                rows = [row for row in rows if (row.get("adjust_type") or "none") == adjust_type_code]
            if start_date:
                rows = [row for row in rows if isinstance(row.get("trade_date"), date) and row["trade_date"] >= start_date]
            if end_date:
                rows = [row for row in rows if isinstance(row.get("trade_date"), date) and row["trade_date"] <= end_date]
            rows = sorted(rows, key=lambda row: _daily_bar_sort_key(row, sort_order=sort_order))
            total = len(rows)
            start = (page - 1) * page_size
            end = start + page_size
            return rows[start:end], total

        result = self._try_duckdb("list_daily_bars", symbol=symbol, market=market, adjust_type=adjust_type_code, start_date=start_date, end_date=end_date, page=page, page_size=page_size, sort_order=sort_order)
        if result is not None:
            return result
        return self._list_daily_bars_pyarrow(
            symbol=symbol, market=market, start_date=start_date, end_date=end_date, page=page, page_size=page_size, sort_order=sort_order,
            adjust_type=adjust_type_code,
        )

    def count(self, *, market: str | None = None) -> int:
        result = self._try_duckdb("count", market=market)
        if result is not None:
            return result
        _, total = self.list_daily_bars(market=market, page=1, page_size=1)
        return total

    def latest_trade_date(self, *, market: str | None = None) -> date | None:
        result = self._try_duckdb("latest_trade_date", market=market)
        if result is not None:
            return result
        rows = self._read_partition_rows(market=market)
        if not rows:
            return None
        return max(row["trade_date"] for row in rows)

    def summarize_symbols(self, *, symbols: list[str], market: str | None = None) -> dict[tuple[str, str], dict]:
        normalized_symbols = sorted({symbol.strip() for symbol in symbols if symbol and symbol.strip()})
        if not normalized_symbols:
            return {}

        result = self._try_duckdb("summarize_symbols", symbols=normalized_symbols, market=market)
        if result is not None:
            return result
        return self._summarize_symbols_pyarrow(symbols=normalized_symbols, market=market)

    def market_trade_dates(self, *, market: str) -> set[date]:
        result = self._try_duckdb("market_trade_dates", market=market)
        if result is not None:
            return result
        rows = self._read_partition_rows(market=market)
        return {
            row["trade_date"]
            for row in rows
            if isinstance(row.get("trade_date"), date)
        }

    def symbol_trade_dates(self, *, symbol: str, market: str) -> set[date]:
        result = self._try_duckdb("symbol_trade_dates", symbol=symbol, market=market)
        if result is not None:
            return result
        rows = self._read_partition_rows(symbol=symbol, market=market)
        return {
            row["trade_date"]
            for row in rows
            if isinstance(row.get("trade_date"), date)
        }

    def symbol_daily_bars(self, *, symbol: str, market: str) -> list[dict]:
        result = self._try_duckdb("symbol_daily_bars", symbol=symbol, market=market)
        if result is not None:
            return result
        rows = self._read_partition_rows(symbol=symbol, market=market)
        return sorted(
            [row for row in rows if isinstance(row.get("trade_date"), date)],
            key=lambda row: (row["trade_date"], row.get("adjust_type") or "none"),
        )

    def market_symbol_trade_date_pairs(self, *, market: str, adjust_type: str | None = None) -> set[tuple[str, date]]:
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type) if adjust_type is not None else None
        result = self._try_duckdb("market_symbol_trade_date_pairs", market=market, adjust_type=adjust_type_code)
        if result is not None:
            return result
        rows = self._read_partition_rows(market=market)
        return {
            (str(row["symbol"]), row["trade_date"])
            for row in rows
            if row.get("symbol") and isinstance(row.get("trade_date"), date)
            if adjust_type_code is None or (row.get("adjust_type") or "none") == adjust_type_code
        }

    def read_all(self) -> list[dict]:
        return self._read_all()

    def _read_all(self) -> list[dict]:
        return self._read_partition_rows()

    def _read_partition_rows(
        self,
        *,
        market: str | None = None,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        if not self.dataset_dir.exists():
            return []

        rows: list[dict] = []
        for path in self._partition_file_paths(market=market, start_date=start_date, end_date=end_date):
            rows.extend(_normalize_row(row) for row in _read_parquet_file(path))

        if market:
            rows = [row for row in rows if row.get("market") == market]
        if symbol:
            rows = [row for row in rows if row.get("symbol") == symbol]
        if start_date:
            rows = [row for row in rows if isinstance(row.get("trade_date"), date) and row["trade_date"] >= start_date]
        if end_date:
            rows = [row for row in rows if isinstance(row.get("trade_date"), date) and row["trade_date"] <= end_date]

        return rows

    def _partition_file_paths(
        self,
        *,
        market: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Path]:
        market_glob = f"market={market}" if market else "market=*"
        paths = []
        for path in self.dataset_dir.glob(f"{market_glob}/trade_date=*/part-*.parquet"):
            partition_trade_date = _partition_trade_date(path)
            if partition_trade_date is None:
                continue
            if start_date and partition_trade_date < start_date:
                continue
            if end_date and partition_trade_date > end_date:
                continue
            paths.append(path)
        return paths

    def _list_daily_bars_pyarrow(
        self,
        *,
        symbol: str | None,
        market: str | None,
        adjust_type: str | None,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
        sort_order: str,
    ) -> tuple[list[dict], int]:
        rows = self._read_partition_rows(
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if adjust_type is not None:
            rows = [row for row in rows if (row.get("adjust_type") or "none") == adjust_type]
        if not rows:
            return [], 0

        rows = sorted(rows, key=lambda row: _daily_bar_sort_key(row, sort_order=sort_order))
        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return rows[start:end], total

    def _list_daily_bars_duckdb(
        self,
        *,
        symbol: str | None,
        market: str | None,
        adjust_type: str | None,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
        sort_order: str,
    ) -> tuple[list[dict], int]:
        where_clause, params = self._duckdb_filters(
            symbol=symbol,
            market=market,
            adjust_type=adjust_type,
            start_date=start_date,
            end_date=end_date,
        )
        direction = "desc" if sort_order == "desc" else "asc"
        con = _duckdb_connect_with_timeout()
        try:
            total = con.execute(
                f"select count(*) from {self._duckdb_scan()} {where_clause}",
                params,
            ).fetchone()[0]
            offset = (page - 1) * page_size
            rows = con.execute(
                f"""
                select {", ".join(DAILY_BAR_COLUMNS)}
                from {self._duckdb_scan()}
                {where_clause}
                order by market asc, symbol asc, trade_date {direction}, adjust_type asc
                limit ? offset ?
                """,
                params + [page_size, offset],
            ).fetchall()
        finally:
            con.close()

        return [_normalize_row(dict(zip(DAILY_BAR_COLUMNS, row))) for row in rows], int(total)

    def _summarize_symbols_pyarrow(self, *, symbols: list[str], market: str | None) -> dict[tuple[str, str], dict]:
        rows = self._read_partition_rows(market=market)
        symbol_set = set(symbols)
        grouped: dict[tuple[str, str], set[date]] = {}
        for row in rows:
            symbol = row.get("symbol")
            trade_date = row.get("trade_date")
            row_market = row.get("market")
            if symbol in symbol_set and row_market and isinstance(trade_date, date):
                grouped.setdefault((str(row_market), str(symbol)), set()).add(trade_date)

        return {
            key: {
                "first_data_date": min(trade_dates),
                "latest_data_date": max(trade_dates),
                "trade_dates_count": len(trade_dates),
            }
            for key, trade_dates in grouped.items()
            if trade_dates
        }

    def _summarize_symbols_duckdb(self, *, symbols: list[str], market: str | None) -> dict[tuple[str, str], dict]:
        conditions = [f"symbol in ({', '.join(['?'] * len(symbols))})"]
        params: list[object] = [str(self.dataset_dir / "market=*" / "trade_date=*" / "part-*.parquet"), *symbols]
        if market:
            conditions.append("market = ?")
            params.append(market)

        con = _duckdb_connect_with_timeout()
        try:
            rows = con.execute(
                f"""
                select
                    market,
                    symbol,
                    min(trade_date) as first_data_date,
                    max(trade_date) as latest_data_date,
                    count(distinct trade_date) as trade_dates_count
                from {self._duckdb_scan()}
                where {" and ".join(conditions)}
                group by market, symbol
                """,
                params,
            ).fetchall()
        finally:
            con.close()

        return {
            (str(row[0]), str(row[1])): {
                "first_data_date": _coerce_date(row[2]),
                "latest_data_date": _coerce_date(row[3]),
                "trade_dates_count": int(row[4] or 0),
            }
            for row in rows
        }

    def _market_trade_dates_duckdb(self, *, market: str) -> set[date]:
        if duckdb is None:
            return {
                row["trade_date"]
                for row in self._read_partition_rows(market=market)
                if isinstance(row.get("trade_date"), date)
            }

        con = _duckdb_connect_with_timeout()
        try:
            rows = con.execute(
                f"""
                select distinct trade_date
                from {self._duckdb_scan()}
                where market = ?
                """,
                [str(self.dataset_dir / "market=*" / "trade_date=*" / "part-*.parquet"), market],
            ).fetchall()
        finally:
            con.close()

        return {_coerce_date(row[0]) for row in rows}

    def _symbol_trade_dates_duckdb(self, *, symbol: str, market: str) -> set[date]:
        if duckdb is None:
            return {
                row["trade_date"]
                for row in self._read_partition_rows(symbol=symbol, market=market)
                if isinstance(row.get("trade_date"), date)
            }

        con = _duckdb_connect_with_timeout()
        try:
            rows = con.execute(
                f"""
                select distinct trade_date
                from {self._duckdb_scan()}
                where market = ? and symbol = ?
                """,
                [str(self.dataset_dir / "market=*" / "trade_date=*" / "part-*.parquet"), market, symbol],
            ).fetchall()
        finally:
            con.close()

        return {_coerce_date(row[0]) for row in rows}

    def _symbol_daily_bars_duckdb(self, *, symbol: str, market: str) -> list[dict]:
        if duckdb is None:
            return sorted(
                self._read_partition_rows(symbol=symbol, market=market),
                key=lambda row: (row["trade_date"], row.get("adjust_type") or "none"),
            )

        settings = get_settings()
        default_lake_root = Path(settings.data_lake_dir)
        default_dataset_dir = default_lake_root / "silver" / "daily_bars"
        uses_default_dataset = (
            self.lake_root.resolve() == default_lake_root.resolve()
            and self.dataset_dir.resolve() == default_dataset_dir.resolve()
        )

        if uses_default_dataset:
            try:
                from backend.app.db.duckdb_store import get_duckdb

                store = get_duckdb(db_path=self.duckdb_path)
                rows = store.execute(
                    f"""
                    select {", ".join(DAILY_BAR_COLUMNS)}
                    from daily_bars
                    where market = ? and symbol = ?
                    order by trade_date asc, adjust_type asc
                    """,
                    [market, symbol],
                ).fetchall()
                if rows:
                    return [_normalize_row(dict(zip(DAILY_BAR_COLUMNS, row))) for row in rows]
            except duckdb.Error:
                pass

        con = _duckdb_connect_with_timeout()
        try:
            rows = con.execute(
                f"""
                select {", ".join(DAILY_BAR_COLUMNS)}
                from {self._duckdb_scan()}
                where market = ? and symbol = ?
                order by trade_date asc, adjust_type asc
                """,
                [str(self.dataset_dir / "market=*" / "trade_date=*" / "part-*.parquet"), market, symbol],
            ).fetchall()
        finally:
            con.close()

        return [_normalize_row(dict(zip(DAILY_BAR_COLUMNS, row))) for row in rows]

    def _market_symbol_trade_date_pairs_duckdb(self, *, market: str, adjust_type: str | None = None) -> set[tuple[str, date]]:
        if duckdb is None:
            return {
                (str(row["symbol"]), row["trade_date"])
                for row in self._read_partition_rows(market=market)
                if row.get("symbol") and isinstance(row.get("trade_date"), date)
                if adjust_type is None or (row.get("adjust_type") or "none") == adjust_type
            }

        conditions = ["market = ?"]
        params: list[object] = [str(self.dataset_dir / "market=*" / "trade_date=*" / "part-*.parquet"), market]
        if adjust_type is not None:
            conditions.append("coalesce(adjust_type, 'none') = ?")
            params.append(adjust_type)

        con = _duckdb_connect_with_timeout()
        try:
            rows = con.execute(
                f"""
                select distinct symbol, trade_date
                from {self._duckdb_scan()}
                where {" and ".join(conditions)}
                """,
                params,
            ).fetchall()
        finally:
            con.close()

        return {(str(row[0]), _coerce_date(row[1])) for row in rows}

    def _count_duckdb(self, *, market: str | None) -> int:
        if duckdb is None:
            return len(self._read_partition_rows(market=market))

        where_clause, params = self._duckdb_filters(
            symbol=None,
            market=market,
            adjust_type=None,
            start_date=None,
            end_date=None,
        )
        con = _duckdb_connect_with_timeout()
        try:
            return int(
                con.execute(
                    f"select count(*) from {self._duckdb_scan()} {where_clause}",
                    params,
                ).fetchone()[0]
            )
        finally:
            con.close()

    def _latest_trade_date_duckdb(self, *, market: str | None) -> date | None:
        if duckdb is None:
            rows = self._read_partition_rows(market=market)
            return max((row["trade_date"] for row in rows), default=None)

        where_clause, params = self._duckdb_filters(
            symbol=None,
            market=market,
            adjust_type=None,
            start_date=None,
            end_date=None,
        )
        con = _duckdb_connect_with_timeout()
        try:
            result = con.execute(
                f"select max(trade_date) from {self._duckdb_scan()} {where_clause}",
                params,
            ).fetchone()[0]
        finally:
            con.close()

        return _coerce_date(result) if result is not None else None

    def _can_query_with_duckdb(self) -> bool:
        return duckdb is not None and any(self.dataset_dir.glob("market=*/trade_date=*/part-*.parquet"))

    def _try_duckdb(self, method_name: str, *args, **kwargs):
        """Try DuckDB path; returns None on failure or if DuckDB unavailable."""
        if not self._can_query_with_duckdb():
            return None
        try:
            return getattr(self, f"_{method_name}_duckdb")(*args, **kwargs)
        except (duckdb.Error, duckdb.IOException):
            return None

    def _duckdb_scan(self) -> str:
        return "read_parquet(?, hive_partitioning=true)"

    def _duckdb_filters(
        self,
        *,
        symbol: str | None,
        market: str | None,
        adjust_type: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[str, list[object]]:
        conditions: list[str] = []
        params: list[object] = [str(self.dataset_dir / "market=*" / "trade_date=*" / "part-*.parquet")]

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if market:
            conditions.append("market = ?")
            params.append(market)
        if adjust_type is not None:
            conditions.append("coalesce(adjust_type, 'none') = ?")
            params.append(adjust_type)
        if start_date:
            conditions.append("trade_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("trade_date <= ?")
            params.append(end_date)

        if not conditions:
            return "", params
        return "where " + " and ".join(conditions), params


DAILY_BAR_ARROW_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string()),
        pa.field("exchange", pa.string()),
        pa.field("market", pa.string()),
        pa.field("trade_date", pa.date32()),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("pre_close", pa.float64()),
        pa.field("volume", pa.float64()),
        pa.field("amount", pa.float64()),
        pa.field("adjust_factor", pa.float64()),
        pa.field("adjust_type", pa.string()),
        pa.field("source", pa.string()),
        pa.field("ingested_at", pa.timestamp("us")),
    ]
)


def _normalize_row(row: dict) -> dict:
    normalized = {column: row.get(column) for column in DAILY_BAR_COLUMNS}
    normalized["trade_date"] = _coerce_date(normalized["trade_date"])
    normalized["adjust_type"] = normalized.get("adjust_type") or "none"
    normalized["ingested_at"] = _coerce_datetime(normalized.get("ingested_at"))
    return normalized


def _daily_bar_sort_key(row: dict, *, sort_order: str) -> tuple:
    trade_date = _coerce_date(row.get("trade_date"))
    if trade_date is None:
        trade_date = date.min
    date_key = -trade_date.toordinal() if sort_order == "desc" else trade_date.toordinal()
    return (row["market"], row["symbol"], date_key, row.get("adjust_type") or "none")


def _read_parquet_file(path: Path) -> list[dict]:
    return pq.ParquetFile(path).read().to_pylist()


def _coerce_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _coerce_datetime(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if value is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _partition_trade_date(path: Path) -> date | None:
    trade_date_part = path.parent.name
    if not trade_date_part.startswith("trade_date="):
        return None

    _, raw_value = trade_date_part.split("=", 1)
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return None
