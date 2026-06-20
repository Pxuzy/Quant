from __future__ import annotations

import importlib.util
from pathlib import Path

from apps.api.core.config import get_settings
from apps.api.db.session import get_database_url


class DatabaseStatusService:
    def get_status(self) -> dict:
        database_url = get_database_url()
        data_lake_path = Path(get_settings().data_lake_dir).expanduser()
        data_lake_stats = _directory_stats(data_lake_path)

        return {
            "database_kind": _database_kind(database_url),
            "database_role": _database_role(database_url),
            "database_note": _database_note(database_url),
            "database_url": _redact_database_url(database_url),
            "database_size_bytes": _sqlite_database_size(database_url),
            "data_lake_path": str(data_lake_path),
            "data_lake_size_bytes": data_lake_stats["size_bytes"],
            "parquet_file_count": data_lake_stats["parquet_file_count"],
            "total_file_count": data_lake_stats["total_file_count"],
            **_duckdb_engine_status(),
        }


def _database_kind(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        return "SQLite"
    if database_url.startswith("postgresql"):
        return "PostgreSQL"
    return database_url.split(":", 1)[0] or "unknown"


def _database_role(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        return "local_fallback"
    if database_url.startswith("postgresql"):
        return "metadata_store"
    return "metadata_store"


def _database_note(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        return (
            "当前元数据库为 SQLite，仅用于本地开发和 bootstrap；生产环境推荐迁移到 PostgreSQL。"
            "行情大表不写入 SQLite，而是存入 Parquet 数据湖；DuckDB 仅作为查询引擎读取 Parquet。"
        )
    if database_url.startswith("postgresql"):
        return (
            "PostgreSQL 元数据库用于股票池、数据源、同步任务、批次、目录和质量报告。"
            "它不是行情大表存储；行情数据存入 Parquet 数据湖，DuckDB 仅作为查询引擎读取 Parquet。"
        )
    return (
        "当前数据库由 DATABASE_URL 指定，建议正式环境使用 PostgreSQL。"
        "行情大表存入 Parquet 数据湖，DuckDB 仅作为查询引擎读取 Parquet。"
    )


def _sqlite_database_size(database_url: str) -> int | None:
    if not database_url.startswith("sqlite:///"):
        return None

    path_value = database_url.removeprefix("sqlite:///")
    if not path_value or path_value == ":memory:":
        return None

    path = Path(path_value).expanduser()
    return path.stat().st_size if path.exists() else 0


def _directory_stats(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"size_bytes": 0, "parquet_file_count": 0, "total_file_count": 0}

    size_bytes = 0
    parquet_file_count = 0
    total_file_count = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        total_file_count += 1
        size_bytes += item.stat().st_size
        if item.suffix.lower() == ".parquet":
            parquet_file_count += 1

    return {
        "size_bytes": size_bytes,
        "parquet_file_count": parquet_file_count,
        "total_file_count": total_file_count,
    }


def _duckdb_engine_status() -> dict[str, str]:
    if importlib.util.find_spec("duckdb") is not None:
        return {
            "duckdb_engine_status": "available",
            "duckdb_engine_note": "DuckDB 查询引擎可用，可用于按需读取 Parquet 数据湖文件。",
        }

    return {
        "duckdb_engine_status": "unavailable",
        "duckdb_engine_note": "DuckDB 查询引擎不可用；请安装 duckdb 包以查询 Parquet 数据湖文件。",
    }


def _redact_database_url(database_url: str) -> str:
    if "@" not in database_url or "://" not in database_url:
        return database_url

    scheme, rest = database_url.split("://", 1)
    _, host_part = rest.rsplit("@", 1)
    return f"{scheme}://***@{host_part}"
