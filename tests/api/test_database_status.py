from __future__ import annotations

from backend.app.core.config import get_settings


def test_database_status_reports_sqlite_and_lake_capacity(client, tmp_path, monkeypatch):
    lake_dir = tmp_path / "lake"
    dataset_dir = lake_dir / "silver" / "daily_bars"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "part-000.parquet").write_bytes(b"12345")
    (lake_dir / "note.txt").write_text("meta", encoding="utf-8")

    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_dir))
    get_settings.cache_clear()

    response = client.get("/api/database/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database_kind"] == "SQLite"
    assert payload["database_role"] == "local_fallback"
    assert "本地开发" in payload["database_note"]
    assert "PostgreSQL" in payload["database_note"]
    assert "Parquet" in payload["database_note"]
    assert "DuckDB" in payload["database_note"]
    assert "查询引擎" in payload["database_note"]
    assert payload["database_size_bytes"] is not None
    assert payload["data_lake_path"] == str(lake_dir)
    assert payload["data_lake_size_bytes"] == 9
    assert payload["parquet_file_count"] == 1
    assert payload["total_file_count"] == 2
    assert payload["duckdb_engine_status"] in {"available", "unavailable"}
    assert "DuckDB" in payload["duckdb_engine_note"]
