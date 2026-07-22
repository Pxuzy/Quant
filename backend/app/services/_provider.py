from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.adapters.base import HealthCheckResult, StockDataSourceAdapter
from backend.app.adapters.registry import AdapterRegistry
from backend.app.repositories.data_sources import DataSourceRepository


class ProviderSelector:
    """Select enabled adapters and maintain provider usage metadata."""

    def __init__(
        self,
        db: Session,
        *,
        registry: AdapterRegistry,
        data_source_repo: DataSourceRepository,
    ) -> None:
        self.db = db
        self.registry = registry
        self.data_source_repo = data_source_repo

    def select(
        self,
        capability: str,
        *,
        require_healthy: bool = True,
    ) -> list[StockDataSourceAdapter]:
        self.data_source_repo.sync_registered_adapters(self.registry)
        candidates: list[StockDataSourceAdapter] = []
        for source in self.data_source_repo.list_enabled():
            try:
                adapter = self.registry.get(source.code)
            except ValueError:
                continue
            if not bool(getattr(adapter.capabilities(), capability, False)):
                continue
            if require_healthy and not self.check_health(adapter).healthy:
                continue
            candidates.append(adapter)

        return sorted(candidates, key=lambda adapter: self._sort_key(adapter, capability))

    def check_health(self, adapter: StockDataSourceAdapter) -> HealthCheckResult:
        health = adapter.health_check()
        self.data_source_repo.update_health(adapter.code, health)
        return health

    def mark_unhealthy(self, code: str, message: str) -> None:
        self.data_source_repo.update_health(
            code,
            HealthCheckResult(healthy=False, status="unhealthy", message=message),
        )

    def record_result(self, code: str, *, success: bool, capability: str) -> None:
        source = self.data_source_repo.get_by_code(code)
        if source is None:
            return

        config = dict(source.config_json) if isinstance(source.config_json, dict) else {}
        stats = dict(config.get("usage_stats", {}))
        cap_stats = dict(stats.get(capability, {"total": 0, "success": 0}))
        cap_stats["total"] = (cap_stats.get("total", 0) or 0) + 1
        if success:
            cap_stats["success"] = (cap_stats.get("success", 0) or 0) + 1
            cap_stats["last_success"] = datetime.now().isoformat()
        else:
            cap_stats["last_failure"] = datetime.now().isoformat()
        stats[capability] = cap_stats
        source.config_json = {**config, "usage_stats": stats}
        self.db.flush()

    def _sort_key(self, adapter: StockDataSourceAdapter, capability: str) -> tuple[float, int]:
        source = self.data_source_repo.get_by_code(adapter.code)
        success_rate = -1.0
        if source is not None:
            config = source.config_json if isinstance(source.config_json, dict) else {}
            cap_stats = config.get("usage_stats", {}).get(capability, {})
            total = cap_stats.get("total", 0) or 0
            if total > 0:
                success_rate = (cap_stats.get("success", 0) or 0) / total
        return -success_rate, adapter.priority


__all__ = ["ProviderSelector"]
