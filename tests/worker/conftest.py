from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import reset_settings_cache  # noqa: E402
from backend.app.db.session import configure_database, init_db  # noqa: E402
from backend.app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Keep worker tests from sharing the process-wide DuckDB connection."""
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "quant.duckdb"))
    reset_settings_cache()
    yield
    reset_settings_cache()
