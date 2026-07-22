from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories._base import BaseRepository

from backend.app.adapters.base import HealthCheckResult, StockDataSourceAdapter
from backend.app.adapters.registry import AdapterRegistry
from backend.app.models import DataSource

LEGACY_DEFAULT_SETTINGS: dict[str, dict[str, object]] = {
    "akshare": {"enabled": False, "priority": 60},
}


class DataSourceRepository(BaseRepository):

    def upsert_adapter(self, adapter: StockDataSourceAdapter) -> DataSource:
        data_source = self.db.scalar(select(DataSource).where(DataSource.code == adapter.code))
        current_config = data_source.config_json if data_source is not None and isinstance(data_source.config_json, dict) else {}
        config_json = {
            **current_config,
            "capabilities": adapter.capabilities().to_dict(),
            "adapter_class": adapter.__class__.__name__,
            "auth_status": adapter.auth_status(),
            "provider_metadata": adapter.metadata().to_dict(),
        }
        if data_source is None:
            data_source = DataSource(
                code=adapter.code,
                name=adapter.name,
                enabled=adapter.default_enabled,
                priority=adapter.priority,
                requires_token=adapter.requires_token,
                config_json=config_json,
            )
            self.db.add(data_source)
        else:
            data_source.name = adapter.name
            data_source.requires_token = adapter.requires_token
            data_source.config_json = config_json
            legacy_defaults = LEGACY_DEFAULT_SETTINGS.get(adapter.code)
            if (
                legacy_defaults is not None
                and data_source.enabled == legacy_defaults["enabled"]
                and data_source.priority == legacy_defaults["priority"]
            ):
                data_source.enabled = adapter.default_enabled
                data_source.priority = adapter.priority
        self.db.flush()
        return data_source

    def sync_registered_adapters(self, registry: AdapterRegistry) -> list[DataSource]:
        registered_codes = {adapter.code for adapter in registry.list()}
        if registered_codes:
            retired_sources = list(
                self.db.scalars(
                    select(DataSource).where(DataSource.code.not_in(registered_codes))
                ).all()
            )
            retired_at = datetime.now(timezone.utc).isoformat()
            for source in retired_sources:
                config_json = source.config_json if isinstance(source.config_json, dict) else {}
                source.enabled = False
                source.health_status = "retired"
                source.config_json = {
                    **config_json,
                    "retired": True,
                    "retired_at": config_json.get("retired_at", retired_at),
                }
        return [self.upsert_adapter(adapter) for adapter in registry.list()]

    def get_by_code(self, code: str) -> DataSource | None:
        return self.db.scalar(select(DataSource).where(DataSource.code == code))

    def list_all(self) -> list[DataSource]:
        sources = list(self.db.scalars(select(DataSource).order_by(DataSource.priority.asc(), DataSource.code.asc())).all())
        return [
            source
            for source in sources
            if not (
                isinstance(source.config_json, dict)
                and source.config_json.get("retired") is True
            )
        ]

    def list_enabled(self) -> list[DataSource]:
        return list(
            self.db.scalars(
                select(DataSource)
                .where(DataSource.enabled.is_(True))
                .order_by(DataSource.priority.asc(), DataSource.code.asc())
            ).all()
        )

    def update_source(self, code: str, *, enabled: bool | None = None, priority: int | None = None) -> DataSource | None:
        data_source = self.get_by_code(code)
        if data_source is None:
            return None
        if enabled is not None:
            data_source.enabled = enabled
        if priority is not None:
            data_source.priority = priority
        self.db.flush()
        return data_source

    def update_health(self, code: str, result: HealthCheckResult) -> None:
        data_source = self.db.scalar(select(DataSource).where(DataSource.code == code))
        if data_source is None:
            return
        data_source.health_status = result.status
        data_source.last_checked_at = datetime.now(timezone.utc)
        config_json = data_source.config_json if isinstance(data_source.config_json, dict) else {}
        data_source.config_json = {**config_json, "last_health_message": result.message}
        self.db.flush()
