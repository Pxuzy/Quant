"""Compatibility exports for market data services."""

from apps.api.services.market_service import (
    get_history_kline,
    get_index_quotes,
    get_news,
    get_realtime_quotes,
    get_sector_rankings,
    get_sector_stocks,
    search_stock,
)

__all__ = [
    "get_realtime_quotes",
    "get_history_kline",
    "get_sector_rankings",
    "get_sector_stocks",
    "get_news",
    "get_index_quotes",
    "search_stock",
]
