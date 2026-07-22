from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    cors_origins: tuple[str, ...]
    data_lake_dir: str
    duckdb_path: str
    repair_parallelism: int


@lru_cache
def get_settings() -> Settings:
    data_lake_dir = os.getenv("DATA_LAKE_DIR", "./storage/lake")
    default_duckdb_path = Path(data_lake_dir).expanduser().resolve() / "quant.duckdb"
    return Settings(
        app_name=os.getenv("APP_NAME", "Quant API"),
        environment=os.getenv("APP_ENV", "local"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./storage/quant.db"),
        cors_origins=parse_csv_env(
            "CORS_ORIGINS",
            ("http://127.0.0.1:5173", "http://localhost:5173"),
        ),
        data_lake_dir=data_lake_dir,
        duckdb_path=os.getenv("DUCKDB_PATH", str(default_duckdb_path)),
        repair_parallelism=int(os.getenv("QUANT_REPAIR_PARALLELISM", "20")),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()


def parse_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default

    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


def ensure_database_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    path_value = database_url.removeprefix("sqlite:///")
    if not path_value or path_value == ":memory:":
        return

    Path(path_value).expanduser().parent.mkdir(parents=True, exist_ok=True)
