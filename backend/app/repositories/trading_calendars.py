from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.adapters.base import NormalizedTradingCalendar
from backend.app.models import TradingCalendar


class TradingCalendarRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_days(
        self,
        *,
        market: str | None,
        start_date: date | None,
        end_date: date | None,
        is_open: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TradingCalendar], int]:
        conditions = []
        if market:
            conditions.append(TradingCalendar.market == market.strip().upper())
        if start_date:
            conditions.append(TradingCalendar.trade_date >= start_date)
        if end_date:
            conditions.append(TradingCalendar.trade_date <= end_date)
        if is_open is not None:
            conditions.append(TradingCalendar.is_open.is_(is_open))

        total_stmt = select(func.count(TradingCalendar.id))
        records_stmt = select(TradingCalendar).order_by(TradingCalendar.market.asc(), TradingCalendar.trade_date.desc())
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        records = self.db.scalars(records_stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(records), total

    def count(self, *, market: str | None = None) -> int:
        stmt = select(func.count(TradingCalendar.id))
        if market:
            stmt = stmt.where(TradingCalendar.market == market.upper())
        return self.db.scalar(stmt) or 0

    def latest_trade_date(self, *, market: str | None = None) -> date | None:
        stmt = select(func.max(TradingCalendar.trade_date))
        if market:
            stmt = stmt.where(TradingCalendar.market == market.upper())
        return self.db.scalar(stmt)

    def open_dates(self, *, market: str, start_date: date, end_date: date) -> list[date]:
        stmt = (
            select(TradingCalendar.trade_date)
            .where(
                TradingCalendar.market == market.strip().upper(),
                TradingCalendar.trade_date >= start_date,
                TradingCalendar.trade_date <= end_date,
                TradingCalendar.is_open.is_(True),
            )
            .order_by(TradingCalendar.trade_date.asc())
        )
        return list(self.db.scalars(stmt).all())

    def upsert_many(self, records: list[NormalizedTradingCalendar]) -> int:
        written = 0
        for record in records:
            day = self.db.scalar(
                select(TradingCalendar).where(
                    TradingCalendar.market == record.market,
                    TradingCalendar.trade_date == record.trade_date,
                )
            )
            if day is None:
                day = TradingCalendar(
                    market=record.market,
                    trade_date=record.trade_date,
                    is_open=record.is_open,
                    source=record.source,
                )
                self.db.add(day)
            else:
                day.is_open = record.is_open
                day.source = record.source
            written += 1
        self.db.flush()
        return written
