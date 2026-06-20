from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from apps.api.models import Stock


BSE_COMMON_STOCK_PREFIXES = ("43", "83", "87", "88", "92")
SSE_COMMON_STOCK_PREFIXES = ("60", "68", "689")
SZSE_COMMON_STOCK_PREFIXES = ("00", "30")


def is_common_stock_symbol(symbol: str, exchange: str | None, market: str) -> bool:
    if market.strip().upper() != "A_SHARE":
        return True

    code = symbol.strip()
    exchange_code = (exchange or "").strip().upper()
    if exchange_code == "SSE":
        return code.startswith(SSE_COMMON_STOCK_PREFIXES)
    if exchange_code == "SZSE":
        return code.startswith(SZSE_COMMON_STOCK_PREFIXES)
    if exchange_code == "BSE":
        return code.startswith(BSE_COMMON_STOCK_PREFIXES)
    return False


def listed_common_stock_filter(market: str | None = None) -> ColumnElement[bool]:
    conditions: list[ColumnElement[bool]] = [Stock.status == "LISTED"]
    if market:
        conditions.append(Stock.market == market.strip().upper())

    return and_(
        *conditions,
        or_(
            and_(
                Stock.market != "A_SHARE",
                Stock.status == "LISTED",
            ),
            and_(
                Stock.market == "A_SHARE",
                or_(
                    and_(
                        Stock.exchange == "SSE",
                        or_(*(Stock.symbol.startswith(prefix) for prefix in SSE_COMMON_STOCK_PREFIXES)),
                    ),
                    and_(
                        Stock.exchange == "SZSE",
                        or_(*(Stock.symbol.startswith(prefix) for prefix in SZSE_COMMON_STOCK_PREFIXES)),
                    ),
                    and_(
                        Stock.exchange == "BSE",
                        or_(*(Stock.symbol.startswith(prefix) for prefix in BSE_COMMON_STOCK_PREFIXES)),
                    ),
                ),
            ),
        ),
    )
