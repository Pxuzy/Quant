from __future__ import annotations

from typing import Any
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class DataSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    enabled: bool
    priority: int
    requires_token: bool
    config_json: dict
    health_status: str
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def auth_status(self) -> str:
        if not self.requires_token:
            return "not_required"
        if isinstance(self.config_json, dict):
            value = self.config_json.get("auth_status")
            if isinstance(value, str) and value:
                return value
        return "unknown"

    @computed_field
    @property
    def capabilities(self) -> dict[str, Any] | None:
        if isinstance(self.config_json, dict):
            value = self.config_json.get("capabilities")
            if isinstance(value, dict):
                return value
        return None

    @computed_field
    @property
    def provider_metadata(self) -> dict[str, Any] | None:
        if isinstance(self.config_json, dict):
            value = self.config_json.get("provider_metadata")
            if isinstance(value, dict):
                return value
        return None

    @computed_field
    @property
    def adapter_class(self) -> str | None:
        if isinstance(self.config_json, dict):
            value = self.config_json.get("adapter_class")
            if isinstance(value, str) and value:
                return value
        return None


class DataSourceUpdate(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)


class DataSourceHealthRead(BaseModel):
    source: DataSourceRead
    healthy: bool
    status: str
    message: str


class DataSourceSmokeRead(BaseModel):
    source: DataSourceRead
    healthy: bool
    status: str
    message: str
    capability: str
    raw_records: int
    normalized_records: int
    validation_errors: list[str]
    sample: list[dict]


class DataSourceCatalogItemRead(BaseModel):
    code: str
    name: str
    source_kind: str
    mcp_role: str | None = None
    integration_status: str
    capabilities: list[str]
    authorization_required: bool
    homepage_url: str | None = None
    docs_url: str | None = None
    mcp_url: str | None = None
    recommended_use: str
    production_note: str
