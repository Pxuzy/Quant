from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.adapters.base import normalize_daily_bar_adjust_type
from backend.app.models import Dataset, DatasetVersion
from backend.app.repositories.daily_bars import (
    DAILY_BAR_ARROW_SCHEMA,
    DAILY_BAR_COLUMNS,
    DailyBarRepository,
    _daily_bar_identity,
    _normalize_row,
    _read_parquet_file,
    parquet_data_lock,
)
from backend.app.repositories.dataset_versions import DatasetVersionRepository
from backend.app.services.dataset_manifest import DatasetManifestStore


@dataclass(frozen=True)
class _PartitionDescriptor:
    key: dict[str, str]
    relative_path: str
    sha256: str
    byte_size: int
    row_count: int
    min_trade_date: date
    max_trade_date: date


class DatasetVersionPublisher:
    """Publish mutable silver Parquet as immutable content-addressed objects."""

    def __init__(self, db: Session, *, lake_root: str | Path, source_repo: DailyBarRepository) -> None:
        self.db = db
        self.lake_root = Path(lake_root).expanduser().resolve()
        self.source_repo = source_repo
        self.version_repo = DatasetVersionRepository(db)
        self.manifest_store = DatasetManifestStore(self.lake_root)

    def publish_daily_bars(self, *, adjust_type: str, source: str | None = None) -> DatasetVersion | None:
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        dataset = self.db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        if dataset is None:
            return None

        with parquet_data_lock(self.source_repo.lake_root):
            descriptors, content_digest = self._materialize_partitions(adjust_type_code)
        if not descriptors:
            return None

        partitions = [
            {
                "key": descriptor.key,
                "uri": descriptor.relative_path,
                "sha256": descriptor.sha256,
                "byte_size": descriptor.byte_size,
                "row_count": descriptor.row_count,
                "min_trade_date": descriptor.min_trade_date.isoformat(),
                "max_trade_date": descriptor.max_trade_date.isoformat(),
            }
            for descriptor in descriptors
        ]
        schema_sha256 = hashlib.sha256(
            json.dumps(DAILY_BAR_COLUMNS, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        bundle_key = self._bundle_key(
            source=source or dataset.source,
            schema_sha256=schema_sha256,
            descriptors=descriptors,
        )
        manifest = {
            "manifest_version": "v1",
            "dataset": "daily_bars",
            "dataset_version_id": f"daily-bars-{adjust_type_code}-{content_digest[:16]}",
            "schema_version": "v1",
            "normalize_version": "v1",
            "schema_sha256": schema_sha256,
            "adjust_type": adjust_type_code,
            "bundle_key": bundle_key,
            "primary_keys": ["symbol", "exchange", "market", "trade_date", "adjust_type"],
            "partition_keys": ["market", "trade_date"],
            "row_count": sum(item.row_count for item in descriptors),
            "min_trade_date": min(item.min_trade_date for item in descriptors).isoformat(),
            "max_trade_date": max(item.max_trade_date for item in descriptors).isoformat(),
            "quality": {"status": "good", "policy": "daily-bars-v1"},
            "lineage": {"source": source or dataset.source},
            "partitions": partitions,
        }
        artifact = self.manifest_store.write(manifest)
        version, _ = self.version_repo.create_candidate(
            dataset=dataset,
            manifest=manifest,
            manifest_artifact=artifact,
        )
        if version.status == "candidate":
            self.version_repo.mark_ready(version)
            self.version_repo.publish(version)
        elif version.status != "published":
            raise RuntimeError(f"content version {version.id} is {version.status}, cannot publish")
        self.db.flush()
        return version

    @staticmethod
    def _bundle_key(*, source: str, schema_sha256: str, descriptors: list[_PartitionDescriptor]) -> str:
        payload = {
            "source": source,
            "schema_version": "v1",
            "normalize_version": "v1",
            "schema_sha256": schema_sha256,
            "quality_policy": "daily-bars-v1",
            "coverage": [
                {
                    "market": item.key["market"],
                    "trade_date": item.key["trade_date"],
                    "row_count": item.row_count,
                }
                for item in descriptors
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _materialize_partitions(self, adjust_type: str) -> tuple[list[_PartitionDescriptor], str]:
        object_root = self.lake_root / "versions" / "_objects" / "daily_bars" / adjust_type
        object_root.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix=".publish-", dir=object_root))
        descriptors: list[_PartitionDescriptor] = []
        try:
            for source_path in self.source_repo._partition_file_paths():
                rows = [
                    _normalize_row(row)
                    for row in _read_parquet_file(source_path)
                    if (row.get("adjust_type") or "none") == adjust_type
                ]
                if not rows:
                    continue
                rows = sorted({_daily_bar_identity(row): row for row in rows}.values(), key=_daily_bar_identity)
                trade_dates = [row["trade_date"] for row in rows]
                market = str(rows[0]["market"])
                trade_date = trade_dates[0]
                logical_path = Path(f"market={market}") / f"trade_date={trade_date.isoformat()}"
                temporary_path = temp_root / logical_path / "part-000.parquet"
                temporary_path.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(pa.Table.from_pylist(rows, schema=DAILY_BAR_ARROW_SCHEMA), temporary_path)
                with temporary_path.open("r+b") as handle:
                    handle.flush()
                    os.fsync(handle.fileno())
                content = temporary_path.read_bytes()
                partition_sha256 = hashlib.sha256(content).hexdigest()
                object_path = object_root / logical_path / f"part-{partition_sha256}.parquet"
                object_path.parent.mkdir(parents=True, exist_ok=True)
                if object_path.exists():
                    if object_path.read_bytes() != content:
                        raise RuntimeError(f"content-addressed partition object mismatch: {object_path}")
                else:
                    os.replace(temporary_path, object_path)
                    self._fsync_directory(object_path.parent)
                descriptors.append(
                    _PartitionDescriptor(
                        key={"market": market, "trade_date": trade_date.isoformat()},
                        relative_path=object_path.relative_to(self.lake_root).as_posix(),
                        sha256=partition_sha256,
                        byte_size=len(content),
                        row_count=len(rows),
                        min_trade_date=min(trade_dates),
                        max_trade_date=max(trade_dates),
                    )
                )

            if not descriptors:
                return [], ""
            descriptors.sort(key=lambda item: item.relative_path)
            content_hash = hashlib.sha256()
            for item in descriptors:
                content_hash.update(item.key["market"].encode("utf-8"))
                content_hash.update(item.key["trade_date"].encode("ascii"))
                content_hash.update(item.sha256.encode("ascii"))
                content_hash.update(str(item.row_count).encode("ascii"))
            return descriptors, content_hash.hexdigest()
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        directory_fd = os.open(path, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
