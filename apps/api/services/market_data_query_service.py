from __future__ import annotations

from datetime import date
from math import ceil
from pathlib import Path

from apps.api.repositories.daily_bars import DailyBarRepository


class MarketDataQueryService:
    def __init__(self, *, lake_root: str | Path | None = None) -> None:
        self.daily_bar_repo = DailyBarRepository(lake_root=lake_root)

    def list_daily_bars(
        self,
        *,
        symbol: str | None,
        market: str | None,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
        sort_order: str = "asc",
    ) -> dict:
        items, total = self.daily_bar_repo.list_daily_bars(
            symbol=symbol,
            market=market,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            sort_order=sort_order,
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
        }
