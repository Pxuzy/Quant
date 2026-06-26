from __future__ import annotations

from datetime import date
from pathlib import Path

from apps.api.repositories.daily_bars import DailyBarRepository


BAR_READER_CONTRACT = {
    "name": "BarReader",
    "dataset": "daily_bars",
    "layer": "silver",
    "adjust_type": "none",
    "source_policy": "governed_only",
}


class ResearchDataService:
    def __init__(self, *, lake_root: str | Path | None = None) -> None:
        self.daily_bar_repo = DailyBarRepository(lake_root=lake_root)

    def read_bars(
        self,
        *,
        symbol: str,
        market: str,
        start_date: date,
        end_date: date,
        page: int = 1,
        page_size: int = 5000,
    ) -> dict:
        symbol_code = symbol.strip()
        market_code = market.strip().upper()
        if not symbol_code:
            raise ValueError("symbol is required.")
        if not market_code:
            raise ValueError("market is required.")
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1.")
        if page_size < 1 or page_size > 10000:
            raise ValueError("page_size must be between 1 and 10000.")

        items, total = self.daily_bar_repo.list_daily_bars(
            symbol=symbol_code,
            market=market_code,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            sort_order="asc",
        )
        return {
            "contract": BAR_READER_CONTRACT,
            "symbol": symbol_code,
            "market": market_code,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "page_size": page_size,
            "items": items,
            "total": total,
        }
