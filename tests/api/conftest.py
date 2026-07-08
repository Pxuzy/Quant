from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.session import configure_database, init_db
from backend.app.main import create_app


@pytest.fixture()
def client(tmp_path):
    configure_database(f"sqlite:///{tmp_path / 'api-test.db'}")
    init_db(drop_all=True)
    with TestClient(create_app()) as test_client:
        yield test_client
