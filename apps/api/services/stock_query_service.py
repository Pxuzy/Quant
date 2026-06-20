from __future__ import annotations

from collections import Counter
from datetime import date
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models import IngestBatch, Stock, TradingCalendar
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.repositories.stocks import StockRepository


class StockQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.stock_repo = StockRepository(db)
        self.daily_bar_repo = DailyBarRepository()

    def list_stocks(
        self,
        *,
        keyword: str | None,
        status: str | None,
        market: str | None,
        page: int,
        page_size: int,
        common_only: bool = True,
    ) -> dict:
        items, total = self.stock_repo.list_stocks(
            keyword=keyword,
            status=status,
            market=market,
            page=page,
            page_size=page_size,
            common_only=common_only,
        )
        enriched_items = self._enrich_with_daily_bar_coverage(items)
        return {
            "items": enriched_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
        }

    def get_stock(self, *, symbol: str, market: str | None = None):
        stock = self.stock_repo.get_stock(symbol=symbol, market=market)
        if stock is None:
            return None
        return self._enrich_with_daily_bar_coverage([stock])[0]

    def get_daily_coverage(self, *, symbol: str, market: str | None = None) -> dict | None:
        stock = self.stock_repo.get_stock(symbol=symbol, market=market)
        if stock is None:
            return None

        summary = self.daily_bar_repo.summarize_symbols(symbols=[stock.symbol], market=stock.market).get(
            (stock.market, stock.symbol)
        )
        if summary is None:
            return _empty_daily_coverage(symbol=stock.symbol, market=stock.market)

        first_data_date = summary["first_data_date"]
        latest_data_date = summary["latest_data_date"]
        expected_dates = sorted(
            trade_date
            for trade_date in (
                self._open_trade_dates(market=stock.market) or self.daily_bar_repo.market_trade_dates(market=stock.market)
            )
            if first_data_date <= trade_date <= latest_data_date
        )
        actual_trade_days = int(summary["trade_dates_count"])
        missing_dates = _missing_trade_dates(
            expected_dates=set(expected_dates),
            actual_dates=self.daily_bar_repo.symbol_trade_dates(symbol=stock.symbol, market=stock.market),
            start_date=first_data_date,
            end_date=latest_data_date,
        )

        return {
            "symbol": stock.symbol,
            "market": stock.market,
            "first_data_date": first_data_date,
            "latest_data_date": latest_data_date,
            "expected_trade_days": len(expected_dates),
            "actual_trade_days": actual_trade_days,
            "missing_trade_days": len(missing_dates),
            "data_completeness": _coverage_ratio(
                actual_count=actual_trade_days,
                expected_dates=set(expected_dates),
                start_date=first_data_date,
                end_date=latest_data_date,
            ),
            "missing_trade_date_samples": missing_dates[:10],
        }

    def get_daily_quality(self, *, symbol: str, market: str | None = None) -> dict | None:
        stock = self.stock_repo.get_stock(symbol=symbol, market=market)
        if stock is None:
            return None

        rows = self.daily_bar_repo.symbol_daily_bars(symbol=stock.symbol, market=stock.market)
        if not rows:
            return _empty_daily_quality(symbol=stock.symbol, market=stock.market)

        trade_dates = sorted({row["trade_date"] for row in rows if isinstance(row.get("trade_date"), date)})
        first_data_date = trade_dates[0]
        latest_data_date = trade_dates[-1]
        expected_dates = sorted(
            trade_date
            for trade_date in (
                self._open_trade_dates(market=stock.market) or self.daily_bar_repo.market_trade_dates(market=stock.market)
            )
            if first_data_date <= trade_date <= latest_data_date
        )
        missing_dates = _missing_trade_dates(
            expected_dates=set(expected_dates),
            actual_dates=set(trade_dates),
            start_date=first_data_date,
            end_date=latest_data_date,
        )
        duplicate_daily_keys = _duplicate_daily_keys(rows)
        ohlc_error_count = 0
        negative_price_count = 0
        negative_volume_count = 0
        negative_amount_count = 0

        for row in rows:
            open_price = _as_float(row.get("open"))
            high_price = _as_float(row.get("high"))
            low_price = _as_float(row.get("low"))
            close_price = _as_float(row.get("close"))
            prices = [open_price, high_price, low_price, close_price]
            negative_price_count += sum(1 for value in prices if value is not None and value < 0)
            if _has_ohlc_error(
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
            ):
                ohlc_error_count += 1
            volume = _as_float(row.get("volume"))
            amount = _as_float(row.get("amount"))
            if volume is not None and volume < 0:
                negative_volume_count += 1
            if amount is not None and amount < 0:
                negative_amount_count += 1

        status = _daily_quality_status(
            checked_rows=len(rows),
            missing_trade_days=len(missing_dates),
            duplicate_daily_keys=duplicate_daily_keys,
            ohlc_error_count=ohlc_error_count,
            negative_price_count=negative_price_count,
            negative_volume_count=negative_volume_count,
            negative_amount_count=negative_amount_count,
        )
        return {
            "symbol": stock.symbol,
            "market": stock.market,
            "status": status,
            "checked_rows": len(rows),
            "first_data_date": first_data_date,
            "latest_data_date": latest_data_date,
            "expected_trade_days": len(expected_dates),
            "actual_trade_days": len(trade_dates),
            "missing_trade_days": len(missing_dates),
            "data_completeness": _coverage_ratio(
                actual_count=len(trade_dates),
                expected_dates=set(expected_dates),
                start_date=first_data_date,
                end_date=latest_data_date,
            ),
            "missing_trade_date_samples": missing_dates[:10],
            "duplicate_daily_keys": duplicate_daily_keys,
            "ohlc_error_count": ohlc_error_count,
            "negative_price_count": negative_price_count,
            "negative_volume_count": negative_volume_count,
            "negative_amount_count": negative_amount_count,
            "adjust_types": sorted({str(row.get("adjust_type") or "none") for row in rows}),
            "sources": sorted({str(row.get("source")) for row in rows if row.get("source")}),
        }

    def get_daily_ingest_batches(self, *, symbol: str, market: str | None = None, limit: int = 5) -> dict | None:
        stock = self.stock_repo.get_stock(symbol=symbol, market=market)
        if stock is None:
            return None

        items = list(
            self.db.scalars(
                select(IngestBatch)
                .where(
                    IngestBatch.dataset_name == "daily_bars",
                    IngestBatch.market == stock.market,
                    IngestBatch.symbol == stock.symbol,
                )
                .order_by(IngestBatch.started_at.desc(), IngestBatch.id.desc())
                .limit(limit)
            ).all()
        )
        return {
            "symbol": stock.symbol,
            "market": stock.market,
            "items": items,
            "total": len(items),
        }

    def _enrich_with_daily_bar_coverage(self, stocks: list[Stock]) -> list[dict]:
        symbols = [stock.symbol for stock in stocks]
        market = _single_market(stocks)
        summaries = self.daily_bar_repo.summarize_symbols(symbols=symbols, market=market)
        market_dates_cache: dict[str, set[date]] = {}

        enriched: list[dict] = []
        for stock in stocks:
            summary = summaries.get((stock.market, stock.symbol))
            latest_data_date = summary["latest_data_date"] if summary else None
            data_completeness = None
            if summary and latest_data_date:
                market_dates = market_dates_cache.setdefault(
                    stock.market,
                    self._open_trade_dates(market=stock.market) or self.daily_bar_repo.market_trade_dates(market=stock.market),
                )
                data_completeness = _coverage_ratio(
                    actual_count=int(summary["trade_dates_count"]),
                    expected_dates=market_dates,
                    start_date=summary["first_data_date"],
                    end_date=latest_data_date,
                )

            enriched.append(
                {
                    "id": stock.id,
                    "symbol": stock.symbol,
                    "exchange": stock.exchange,
                    "market": stock.market,
                    "name": stock.name,
                    "status": stock.status,
                    "industry": stock.industry,
                    "listing_date": stock.listing_date,
                    "delisting_date": stock.delisting_date,
                    "source": stock.source,
                    "latest_data_date": latest_data_date,
                    "data_completeness": data_completeness,
                    "created_at": stock.created_at,
                    "updated_at": stock.updated_at,
                }
            )
        return enriched

    def _open_trade_dates(self, *, market: str) -> set[date]:
        rows = self.db.scalars(
            select(TradingCalendar.trade_date).where(
                TradingCalendar.market == market,
                TradingCalendar.is_open.is_(True),
            )
        ).all()
        return set(rows)


def _single_market(stocks: list[Stock]) -> str | None:
    markets = {stock.market for stock in stocks}
    return next(iter(markets)) if len(markets) == 1 else None


def _coverage_ratio(*, actual_count: int, expected_dates: set[date], start_date: date, end_date: date) -> float | None:
    expected_count = sum(1 for trade_date in expected_dates if start_date <= trade_date <= end_date)
    if expected_count <= 0:
        return None
    return min(1.0, round(actual_count / expected_count, 4))


def _empty_daily_coverage(*, symbol: str, market: str) -> dict:
    return {
        "symbol": symbol,
        "market": market,
        "first_data_date": None,
        "latest_data_date": None,
        "expected_trade_days": 0,
        "actual_trade_days": 0,
        "missing_trade_days": 0,
        "data_completeness": None,
        "missing_trade_date_samples": [],
    }


def _empty_daily_quality(*, symbol: str, market: str) -> dict:
    return {
        "symbol": symbol,
        "market": market,
        "status": "unknown",
        "checked_rows": 0,
        "first_data_date": None,
        "latest_data_date": None,
        "expected_trade_days": 0,
        "actual_trade_days": 0,
        "missing_trade_days": 0,
        "data_completeness": None,
        "missing_trade_date_samples": [],
        "duplicate_daily_keys": 0,
        "ohlc_error_count": 0,
        "negative_price_count": 0,
        "negative_volume_count": 0,
        "negative_amount_count": 0,
        "adjust_types": [],
        "sources": [],
    }


def _missing_trade_dates(
    *,
    expected_dates: set[date],
    actual_dates: set[date],
    start_date: date,
    end_date: date,
) -> list[date]:
    return sorted(
        trade_date
        for trade_date in expected_dates
        if start_date <= trade_date <= end_date and trade_date not in actual_dates
    )


def _duplicate_daily_keys(rows: list[dict]) -> int:
    keys = [
        (
            row.get("market"),
            row.get("symbol"),
            row.get("exchange"),
            row.get("trade_date"),
            row.get("adjust_type") or "none",
        )
        for row in rows
        if row.get("market") and row.get("symbol") and row.get("exchange") and row.get("trade_date")
    ]
    return sum(count - 1 for count in Counter(keys).values() if count > 1)


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_ohlc_error(
    *,
    open_price: float | None,
    high_price: float | None,
    low_price: float | None,
    close_price: float | None,
) -> bool:
    if high_price is not None and low_price is not None and high_price < low_price:
        return True
    if high_price is not None and any(
        value is not None and high_price < value for value in (open_price, close_price)
    ):
        return True
    if low_price is not None and any(
        value is not None and low_price > value for value in (open_price, close_price)
    ):
        return True
    return False


def _daily_quality_status(
    *,
    checked_rows: int,
    missing_trade_days: int,
    duplicate_daily_keys: int,
    ohlc_error_count: int,
    negative_price_count: int,
    negative_volume_count: int,
    negative_amount_count: int,
) -> str:
    if checked_rows <= 0:
        return "unknown"
    if any(
        count > 0
        for count in (
            duplicate_daily_keys,
            ohlc_error_count,
            negative_price_count,
            negative_volume_count,
            negative_amount_count,
        )
    ):
        return "error"
    if missing_trade_days > 0:
        return "warning"
    return "good"
