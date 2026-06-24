from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from apps.api.adapters.base import NormalizedStock
from apps.api.core.market_symbols import is_common_stock_symbol, listed_common_stock_filter
from apps.api.models import Stock


class StockRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_stocks(
        self,
        *,
        keyword: str | None,
        status: str | None,
        market: str | None,
        page: int | None,
        page_size: int | None,
        exchange: str | None = None,
        industry: str | None = None,
        common_only: bool = False,
    ) -> tuple[list[Stock], int]:
        conditions = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    Stock.symbol.ilike(pattern),
                    Stock.name.ilike(pattern),
                    Stock.industry.ilike(pattern),
                )
            )
        if exchange:
            conditions.append(Stock.exchange == exchange.strip().upper())
        if industry:
            conditions.append(Stock.industry.ilike(f"%{industry.strip()}%"))
        if status:
            conditions.append(Stock.status == status)
        if market:
            conditions.append(Stock.market == market)
        if common_only:
            conditions.append(listed_common_stock_filter(market=market))

        total_stmt = select(func.count(Stock.id))
        records_stmt = select(Stock).order_by(Stock.market, Stock.exchange, Stock.symbol)
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        if page is not None and page_size is not None:
            records_stmt = records_stmt.offset((page - 1) * page_size).limit(page_size)
        records = self.db.scalars(records_stmt).all()
        return list(records), total

    def count(self, *, market: str | None = None, common_only: bool = False) -> int:
        stmt = select(func.count(Stock.id))
        if market:
            stmt = stmt.where(Stock.market == market.strip().upper())
        if common_only:
            stmt = stmt.where(listed_common_stock_filter(market=market))
        return self.db.scalar(stmt) or 0

    def get_stock(self, *, symbol: str, market: str | None = None) -> Stock | None:
        normalized_market = market.strip().upper() if market else None
        stmt = select(Stock).where(Stock.symbol == symbol.strip()).order_by(Stock.market, Stock.exchange)
        if market:
            stmt = stmt.where(Stock.market == normalized_market)

        stocks = list(self.db.scalars(stmt).all())
        if normalized_market == "A_SHARE":
            common_stock = next(
                (
                    stock
                    for stock in stocks
                    if is_common_stock_symbol(stock.symbol, stock.exchange, stock.market)
                    and stock.status == "LISTED"
                ),
                None,
            )
            if common_stock is not None:
                return common_stock
        return stocks[0] if stocks else None

    def list_market_stocks(
        self,
        *,
        market: str,
        status: str | None = "LISTED",
        limit: int | None = None,
        common_only: bool = False,
    ) -> list[Stock]:
        stmt = select(Stock).where(Stock.market == market.strip().upper()).order_by(Stock.exchange, Stock.symbol)
        if status:
            stmt = stmt.where(Stock.status == status)
        if common_only:
            stmt = stmt.where(listed_common_stock_filter(market=market))
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def upsert_many(self, records: list[NormalizedStock]) -> int:
        written = 0
        for record in records:
            stock = self.db.scalar(
                select(Stock).where(
                    Stock.symbol == record.symbol,
                    Stock.exchange == record.exchange,
                    Stock.market == record.market,
                )
            )
            if stock is None:
                stock = Stock(
                    symbol=record.symbol,
                    exchange=record.exchange,
                    market=record.market,
                    name=record.name,
                    status=record.status,
                    industry=record.industry,
                    listing_date=record.listing_date,
                    delisting_date=record.delisting_date,
                    source=record.source,
                )
                self.db.add(stock)
            else:
                stock.name = record.name
                stock.status = record.status
                stock.industry = record.industry
                stock.listing_date = record.listing_date
                stock.delisting_date = record.delisting_date
                stock.source = record.source
            written += 1
        self.db.flush()
        return written
