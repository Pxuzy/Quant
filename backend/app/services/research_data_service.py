from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.adapters.base import normalize_daily_bar_adjust_type
from backend.app.models import Dataset, IngestBatch, Snapshot, SnapshotMember
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.services.dataset_manifest import manifest_sha256, validate_manifest


BAR_READER_CONTRACT = {
    "name": "BarReader",
    "dataset": "daily_bars",
    "layer": "silver",
    "adjust_type": "none",
    "source_policy": "governed_only",
}


class ResearchDataService:
    def __init__(self, db: Session | None = None, *, lake_root: str | Path | None = None) -> None:
        self.db = db
        self.daily_bar_repo = DailyBarRepository(lake_root=lake_root)

    def read_bars(
        self,
        *,
        symbol: str,
        market: str,
        start_date: date,
        end_date: date,
        adjust_type: str = "none",
        snapshot_id: int | None = None,
        page: int = 1,
        page_size: int = 5000,
    ) -> dict:
        symbol_code = symbol.strip()
        market_code = market.strip().upper()
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        if not symbol_code:
            raise ValueError("symbol is required.")
        if not market_code:
            raise ValueError("market is required.")
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1.")
        if page_size < 1 or page_size > 10000:
            raise ValueError("page_size must be between 1 and 10000.")

        reader_repo = self.daily_bar_repo
        snapshot_binding = None
        if snapshot_id is not None:
            reader_repo, snapshot_binding = self._snapshot_reader(
                snapshot_id=snapshot_id,
                adjust_type=adjust_type_code,
            )

        items, total = reader_repo.list_daily_bars(
            symbol=symbol_code,
            market=market_code,
            adjust_type=adjust_type_code,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            sort_order="asc",
        )
        return {
            "contract": self._bar_reader_contract(
                adjust_type=adjust_type_code,
                snapshot_binding=snapshot_binding,
            ),
            "symbol": symbol_code,
            "market": market_code,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "page_size": page_size,
            "items": items,
            "total": total,
        }

    def _bar_reader_contract(self, *, adjust_type: str, snapshot_binding: dict | None = None) -> dict:
        manifest = (
            snapshot_binding["manifest"]
            if snapshot_binding is not None
            else self._daily_bars_manifest(adjust_type=adjust_type)
        )
        contract = {
            **BAR_READER_CONTRACT,
            "adjust_type": adjust_type,
            "manifest": manifest,
        }
        if snapshot_binding is not None:
            contract.update(
                snapshot_id=snapshot_binding["snapshot_id"],
                dataset_version_id=snapshot_binding["dataset_version_id"],
                manifest_sha256=snapshot_binding["manifest_sha256"],
            )
        return contract

    def _snapshot_reader(self, *, snapshot_id: int, adjust_type: str) -> tuple[DailyBarRepository, dict]:
        if self.db is None:
            raise ValueError("snapshot_id requires a database-backed research reader.")
        snapshot = self.db.get(Snapshot, snapshot_id)
        if snapshot is None:
            raise ValueError(f"Snapshot {snapshot_id} does not exist.")
        if snapshot.status not in {"active", "retired"}:
            raise ValueError(f"Snapshot {snapshot_id} is {snapshot.status}, expected active or retired.")

        role = f"bars-{adjust_type}"
        member = self.db.scalar(
            select(SnapshotMember).where(
                SnapshotMember.snapshot_id == snapshot.id,
                SnapshotMember.role == role,
            )
        )
        if member is None and adjust_type == "none":
            member = self.db.scalar(
                select(SnapshotMember).where(
                    SnapshotMember.snapshot_id == snapshot.id,
                    SnapshotMember.role == "bars",
                )
            )
        if member is None:
            raise ValueError(f"Snapshot {snapshot_id} has no member for adjust_type={adjust_type}.")
        version = member.dataset_version
        if version.status != "published":
            raise ValueError(f"Snapshot {snapshot_id} references unpublished dataset version {version.id}.")
        if version.adjust_type != adjust_type:
            raise ValueError(
                f"Snapshot {snapshot_id} member {member.role} has adjust_type={version.adjust_type}, "
                f"requested {adjust_type}."
            )

        manifest = self._validate_snapshot_manifest(version)
        version_root = self._validate_snapshot_partitions(version.partitions, manifest=manifest)
        reader_repo = DailyBarRepository(
            lake_root=self.daily_bar_repo.lake_root,
            dataset_dir=version_root,
            partition_paths=[
                (self.daily_bar_repo.lake_root / partition.relative_uri).resolve()
                for partition in version.partitions
            ],
        )
        return reader_repo, {
            "snapshot_id": snapshot.id,
            "dataset_version_id": version.id,
            "manifest_sha256": version.manifest_sha256,
            "manifest": {
                "dataset_name": "daily_bars",
                "layer": "silver",
                "storage_type": "parquet",
                "source": "snapshot",
                "row_count": version.row_count,
                "latest_data_date": version.max_trade_date,
                "quality_status": version.quality_status,
                "updated_at": version.published_at,
                "latest_ingest_batch": None,
                "dataset_version_id": version.id,
                "manifest_uri": version.manifest_uri,
                "manifest_sha256": version.manifest_sha256,
                "bundle_key": version.bundle_key,
            },
        }

    def _validate_snapshot_manifest(self, version) -> dict:
        lake_root = self.daily_bar_repo.lake_root.resolve()
        relative_uri = Path(version.manifest_uri)
        if relative_uri.is_absolute() or ".." in relative_uri.parts:
            raise ValueError("snapshot manifest URI escapes the configured data lake")
        path = (lake_root / relative_uri).resolve()
        try:
            path.relative_to(lake_root)
        except ValueError as exc:
            raise ValueError("snapshot manifest path escapes the configured data lake") from exc
        if not path.is_file():
            raise ValueError(f"snapshot manifest is missing: {version.manifest_uri}")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            validate_manifest(manifest)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"snapshot manifest is invalid: {version.manifest_uri}") from exc
        if manifest_sha256(manifest) != version.manifest_sha256:
            raise ValueError(f"snapshot manifest checksum mismatch: {version.manifest_uri}")
        if manifest.get("adjust_type") != version.adjust_type:
            raise ValueError("snapshot manifest adjust_type does not match dataset version")
        if manifest.get("dataset") != version.dataset.name:
            raise ValueError("snapshot manifest dataset does not match dataset version")
        if manifest.get("schema_version") != version.schema_version:
            raise ValueError("snapshot manifest schema version does not match dataset version")
        if manifest.get("normalize_version") != version.normalize_version:
            raise ValueError("snapshot manifest normalize version does not match dataset version")
        if manifest.get("schema_sha256") != version.schema_sha256:
            raise ValueError("snapshot manifest schema checksum does not match dataset version")
        if manifest.get("bundle_key") != version.bundle_key:
            raise ValueError("snapshot manifest bundle_key does not match dataset version")
        manifest_uri_list = [str(item["uri"]) for item in manifest["partitions"]]
        database_uri_list = [partition.relative_uri for partition in version.partitions]
        if len(manifest_uri_list) != len(set(manifest_uri_list)):
            raise ValueError("snapshot manifest contains duplicate partition URIs")
        if len(database_uri_list) != len(set(database_uri_list)):
            raise ValueError("snapshot dataset version contains duplicate partition URIs")
        if set(manifest_uri_list) != set(database_uri_list):
            raise ValueError("snapshot manifest and dataset version partition URI sets differ")
        if manifest.get("row_count") != version.row_count:
            raise ValueError("snapshot manifest does not match dataset version metadata")
        return manifest

    def _validate_snapshot_partitions(self, partitions, *, manifest: dict) -> Path:
        if not partitions:
            raise ValueError("snapshot dataset version has no partitions")
        lake_root = self.daily_bar_repo.lake_root.resolve()
        roots: set[Path] = set()
        manifest_partitions = {str(item["uri"]): item for item in manifest["partitions"]}
        database_row_count = 0
        for partition in partitions:
            if partition.status != "sealed":
                raise ValueError(f"snapshot partition is not sealed: {partition.relative_uri}")
            relative_uri = Path(partition.relative_uri)
            if relative_uri.is_absolute() or ".." in relative_uri.parts:
                raise ValueError("snapshot partition URI escapes the configured data lake")
            parts = relative_uri.parts
            try:
                market_index = next(index for index, part in enumerate(parts) if part.startswith("market="))
            except StopIteration as exc:
                raise ValueError("snapshot partition URI must contain a market= path component") from exc
            root = lake_root.joinpath(*parts[:market_index]).resolve()
            try:
                root.relative_to(lake_root)
            except ValueError as exc:
                raise ValueError("snapshot partition root escapes the configured data lake") from exc
            roots.add(root)
            path = (lake_root / relative_uri).resolve()
            try:
                path.relative_to(lake_root)
            except ValueError as exc:
                raise ValueError("snapshot partition path escapes the configured data lake") from exc
            if not path.is_file():
                raise ValueError(f"snapshot partition is missing: {relative_uri}")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != partition.sha256:
                raise ValueError(f"snapshot partition checksum mismatch: {relative_uri}")
            if len(content) != partition.byte_size:
                raise ValueError(f"snapshot partition byte size mismatch: {relative_uri}")
            if pq.ParquetFile(path).metadata.num_rows != partition.row_count:
                raise ValueError(f"snapshot partition row count mismatch: {relative_uri}")
            manifest_partition = manifest_partitions.get(partition.relative_uri)
            if manifest_partition is None:
                raise ValueError(f"snapshot partition is absent from manifest: {relative_uri}")
            if (
                manifest_partition["sha256"] != partition.sha256
                or manifest_partition["byte_size"] != partition.byte_size
                or manifest_partition["row_count"] != partition.row_count
            ):
                raise ValueError(f"snapshot partition metadata differs from manifest: {relative_uri}")
            if dict(manifest_partition.get("key") or {}) != dict(partition.partition_spec_json or {}):
                raise ValueError(f"snapshot partition key differs from manifest: {relative_uri}")
            if manifest_partition.get("min_trade_date") != (
                partition.min_trade_date.isoformat() if partition.min_trade_date else None
            ):
                raise ValueError(f"snapshot partition minimum date differs from manifest: {relative_uri}")
            if manifest_partition.get("max_trade_date") != (
                partition.max_trade_date.isoformat() if partition.max_trade_date else None
            ):
                raise ValueError(f"snapshot partition maximum date differs from manifest: {relative_uri}")
            database_row_count += partition.row_count
        if database_row_count != manifest["row_count"]:
            raise ValueError("snapshot partition row counts do not match manifest total")
        if len(roots) != 1:
            raise ValueError("snapshot dataset version partitions must share one dataset root")
        return next(iter(roots))

    def _daily_bars_manifest(self, *, adjust_type: str = "none") -> dict:
        if self.db is None:
            return {
                "dataset_name": "daily_bars",
                "layer": "silver",
                "storage_type": "parquet",
                "source": "unknown",
                "row_count": 0,
                "latest_data_date": None,
                "quality_status": "unknown",
                "updated_at": None,
                "latest_ingest_batch": None,
            }

        dataset = self.db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        if dataset is None:
            return {
                "dataset_name": "daily_bars",
                "layer": "silver",
                "storage_type": "parquet",
                "source": "unknown",
                "row_count": 0,
                "latest_data_date": None,
                "quality_status": "missing",
                "updated_at": None,
                "latest_ingest_batch": None,
            }

        return {
            "dataset_name": dataset.name,
            "layer": dataset.layer,
            "storage_type": dataset.storage_type,
            "source": dataset.source,
            "row_count": dataset.row_count,
            "latest_data_date": dataset.latest_data_date,
            "quality_status": dataset.quality_status,
            "updated_at": dataset.updated_at,
            "latest_ingest_batch": self._latest_daily_bars_ingest_batch(),
        }

    def _latest_daily_bars_ingest_batch(self) -> dict | None:
        if self.db is None:
            return None

        batch = self.db.scalar(
            select(IngestBatch)
            .where(IngestBatch.dataset_name == "daily_bars", IngestBatch.status == "success")
            .order_by(func.coalesce(IngestBatch.finished_at, IngestBatch.started_at).desc(), IngestBatch.id.desc())
            .limit(1)
        )
        if batch is None:
            return None

        return {
            "id": batch.id,
            "task_id": batch.task_id,
            "source": batch.source,
            "requested_source": batch.requested_source,
            "market": batch.market,
            "symbol": batch.symbol,
            "start_date": batch.start_date,
            "end_date": batch.end_date,
            "status": batch.status,
            "schema_version": batch.schema_version,
            "normalize_version": batch.normalize_version,
            "records_written": batch.records_written,
            "quality_status": batch.quality_status,
        }
