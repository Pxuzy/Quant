from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.adapters.base import StockDataSourceAdapter, normalize_daily_bar_adjust_type
from backend.app.core.market_symbols import is_common_stock_symbol
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.repositories.stocks import StockRepository
from backend.app.repositories.trading_calendars import TradingCalendarRepository

DEFAULT_MARKET_REPAIR_START_POLICY = "requested_start"
LISTING_DATE_START_POLICY = "listing_date"


@dataclass(frozen=True)
class MarketRepairPlanItem:
    symbol: str
    exchange: str
    name: str
    start_date: date
    end_date: date
    missing_trade_days: int


@dataclass(frozen=True)
class MarketRepairPlan:
    source: str
    market: str
    start_date: date
    end_date: date
    max_symbols: int
    start_policy: str
    adjust_type: str
    stock_pool_count: int
    open_dates_count: int
    planned_missing_symbol_days: int
    supported_exchanges: list[str] | None
    items: list[MarketRepairPlanItem]

    @property
    def planned_symbols(self) -> int:
        return len(self.items)


class MarketRepairPlanner:
    def __init__(
        self,
        *,
        stock_repo: StockRepository,
        trading_calendar_repo: TradingCalendarRepository,
        daily_bar_repo: DailyBarRepository,
    ) -> None:
        self.stock_repo = stock_repo
        self.trading_calendar_repo = trading_calendar_repo
        self.daily_bar_repo = daily_bar_repo

    def build_plan(
        self,
        *,
        adapter: StockDataSourceAdapter,
        market: str,
        start_date: date,
        end_date: date,
        max_symbols: int,
        start_policy: str = DEFAULT_MARKET_REPAIR_START_POLICY,
        adjust_type: str = "none",
    ) -> MarketRepairPlan:
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        supported_exchanges = _daily_bar_exchanges(adapter)
        stocks = [
            stock
            for stock in self.stock_repo.list_market_stocks(market=market, status="LISTED", common_only=True)
            if supported_exchanges is None or stock.exchange in supported_exchanges
            if is_common_stock_symbol(stock.symbol, stock.exchange, market)
        ]
        if not stocks:
            raise RuntimeError(f"股票池没有 {market} 已上市股票，请先同步股票池。")

        open_dates = self.trading_calendar_repo.open_dates(market=market, start_date=start_date, end_date=end_date)
        if not open_dates:
            raise RuntimeError("交易日历在该范围内没有开市日，请先同步交易日历。")

        existing_pairs = self.daily_bar_repo.market_symbol_trade_date_pairs(market=market, adjust_type=adjust_type_code)
        items: list[MarketRepairPlanItem] = []
        for stock in stocks:
            symbol_start_date = symbol_repair_start_date(
                stock_listing_date=stock.listing_date,
                requested_start_date=start_date,
                start_policy=start_policy,
            )
            missing_dates = [
                trade_date
                for trade_date in open_dates
                if trade_date >= symbol_start_date and (stock.symbol, trade_date) not in existing_pairs
            ]
            if not missing_dates:
                continue
            items.append(
                MarketRepairPlanItem(
                    symbol=stock.symbol,
                    exchange=stock.exchange,
                    name=stock.name,
                    start_date=min(missing_dates),
                    end_date=max(missing_dates),
                    missing_trade_days=len(missing_dates),
                )
            )
            if len(items) >= max_symbols:
                break

        return MarketRepairPlan(
            source=adapter.code,
            market=market,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type_code,
            stock_pool_count=len(stocks),
            open_dates_count=len(open_dates),
            planned_missing_symbol_days=sum(item.missing_trade_days for item in items),
            supported_exchanges=sorted(supported_exchanges) if supported_exchanges is not None else None,
            items=items,
        )


def symbol_repair_start_date(
    *,
    stock_listing_date: date | None,
    requested_start_date: date,
    start_policy: str,
) -> date:
    if start_policy == LISTING_DATE_START_POLICY and stock_listing_date is not None:
        return max(requested_start_date, stock_listing_date)
    return requested_start_date


def _daily_bar_exchanges(adapter: StockDataSourceAdapter) -> set[str] | None:
    exchanges = adapter.capabilities().daily_bar_exchanges
    if exchanges is None:
        return None
    return {exchange.strip().upper() for exchange in exchanges if exchange.strip()}
