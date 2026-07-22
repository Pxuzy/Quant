from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas import PaginatedResponse


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    layer: str
    storage_type: str
    path: str | None
    data_schema: dict = Field(validation_alias="schema_json", serialization_alias="schema_json")
    primary_keys_json: list[str]
    partition_keys_json: list[str]
    source: str
    row_count: int
    latest_data_date: date | None
    quality_status: str
    updated_at: datetime


PaginatedDatasets = PaginatedResponse[DatasetRead]
