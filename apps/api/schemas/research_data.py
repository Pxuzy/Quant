from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from apps.api.schemas.market_data import DailyBarRead


class ResearchDataContractRead(BaseModel):
    name: str
    dataset: str
    layer: str
    adjust_type: str
    source_policy: str


class ResearchBarsRead(BaseModel):
    contract: ResearchDataContractRead
    symbol: str
    market: str
    start_date: date
    end_date: date
    page: int
    page_size: int
    items: list[DailyBarRead]
    total: int
