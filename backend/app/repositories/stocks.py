from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.repositories._base import BaseRepository

from backend.app.adapters.base import NormalizedStock
from backend.app.core.market_symbols import is_common_stock_symbol, listed_common_stock_filter
from backend.app.models import Stock
from backend.app.repositories._query import paginated_query


class StockRepository(BaseRepository):

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
        has_data: bool | None = None,
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
        if has_data:
            conditions.append(Stock.latest_data_date.isnot(None))
        if has_data is False:
            conditions.append(Stock.latest_data_date.is_(None))

        total_stmt = select(func.count(Stock.id))
        # Default: stocks with most recent data first, then by symbol
        records_stmt = select(Stock).order_by(
            Stock.updated_at.desc().nulls_last(),
            Stock.symbol.asc(),
        )
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

    def list_industry_groups(self, *, market: str = "A_SHARE", common_only: bool = True) -> list[tuple[str, int]]:
        stmt = (
            select(Stock.industry, func.count(Stock.id))
            .where(Stock.market == market.strip().upper())
            .where(Stock.industry.is_not(None), func.trim(Stock.industry) != "")
            .group_by(Stock.industry)
            .order_by(func.count(Stock.id).desc(), Stock.industry)
        )
        if common_only:
            stmt = stmt.where(listed_common_stock_filter(market=market))
        return [(industry, count) for industry, count in self.db.execute(stmt).all()]

    def list_stocks_by_industry(
        self,
        *,
        industry: str,
        market: str = "A_SHARE",
        status: str | None = "LISTED",
        limit: int | None = None,
        common_only: bool = True,
    ) -> list[Stock]:
        stmt = (
            select(Stock)
            .where(Stock.market == market.strip().upper(), Stock.industry == industry.strip())
            .order_by(Stock.exchange, Stock.symbol)
        )
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
                if record.industry is not None:
                    stock.industry = record.industry
                stock.listing_date = record.listing_date
                stock.delisting_date = record.delisting_date
                stock.source = record.source
            written += 1
        self.db.flush()
        return written

    def update_industries(self, industry_by_symbol: dict[tuple[str, str, str], str]) -> int:
        if not industry_by_symbol:
            return 0
        updated = 0
        stmt = select(Stock).where(Stock.market == "A_SHARE", Stock.status == "LISTED")
        for stock in self.db.scalars(stmt).all():
            key = (stock.symbol, stock.exchange, stock.market)
            industry = industry_by_symbol.get(key)
            if industry and stock.industry != industry:
                stock.industry = industry
                updated += 1
        self.db.flush()
        return updated

    def update_data_freshness(
        self,
        *,
        symbol: str,
        exchange: str | None = None,
        market: str = "A_SHARE",
        latest_data_date,
        data_completeness: float | None = None,
    ) -> None:
        """更新股票的最新数据日期和完整度。"""
        conditions = [Stock.symbol == symbol.strip(), Stock.market == market.strip().upper()]
        if exchange:
            conditions.append(Stock.exchange == exchange.strip().upper())
        stock = self.db.scalar(select(Stock).where(*conditions))
        if stock is not None:
            if latest_data_date is not None:
                if stock.latest_data_date is None or latest_data_date > stock.latest_data_date:
                    stock.latest_data_date = latest_data_date
            if data_completeness is not None:
                stock.data_completeness = data_completeness
            self.db.flush()
