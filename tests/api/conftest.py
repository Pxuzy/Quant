from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import reset_settings_cache  # noqa: E402
from backend.app.db.session import configure_database, init_db  # noqa: E402
from backend.app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Give every API test a private SQLite, DuckDB, and Parquet storage root."""
    reset_settings_cache()
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "quant.duckdb"))
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture()
def fake_akshare(monkeypatch):
    """Provide deterministic adapter availability without optional network packages."""
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(
            stock_info_a_code_name=lambda: [],
            stock_zh_a_hist=lambda **kwargs: [],
        ),
    )


@pytest.fixture()
def client(tmp_path):
    configure_database(f"sqlite:///{tmp_path / 'api-test.db'}")
    init_db(drop_all=True)
    with TestClient(create_app()) as test_client:
        yield test_client
