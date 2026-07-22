"""Pipeline orchestration helpers and shared constants for the market-data sync stack.

The actual ``DailyBarIngestPipeline`` implementation lives in
``apps.api.services.daily_bar_ingest_pipeline``.  This module re-exports it
and hosts the shared constants used by both :mod:`sync_service` and
:mod:`repair_service`, keeping the dependency graph acyclic:

    pipeline  (no internal deps)
      ^
      |
  repair_service  (depends on pipeline only)
      ^
      |
  sync_service  (depends on pipeline + repair_service)
"""

from __future__ import annotations

from backend.app.services.daily_bar_ingest_pipeline import DailyBarIngestPipeline

MARKET_REPAIR_TASK_TYPE = "daily_bars_market_repair"
DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20
MAX_MARKET_REPAIR_SYMBOLS = 5000
DEFAULT_ADJUST_TYPE = "none"

__all__ = [
    "DailyBarIngestPipeline",
    "DEFAULT_ADJUST_TYPE",
    "DEFAULT_MARKET_REPAIR_MAX_SYMBOLS",
    "MARKET_REPAIR_TASK_TYPE",
    "MAX_MARKET_REPAIR_SYMBOLS",
]
