from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetVersion, DatasetVersionPartition
from backend.app.services.dataset_manifest import ManifestArtifact, validate_manifest


class DatasetVersionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_candidate(
        self,
        *,
        dataset: Dataset,
        manifest: Mapping[str, Any],
        manifest_artifact: ManifestArtifact,
    ) -> tuple[DatasetVersion, bool]:
        validate_manifest(manifest)
        existing = self.db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset.id,
                DatasetVersion.manifest_sha256 == manifest_artifact.sha256,
            )
        )
        if existing is not None:
            return existing, False

        next_sequence = (
            self.db.scalar(
                select(func.coalesce(func.max(DatasetVersion.version_seq), 0)).where(
                    DatasetVersion.dataset_id == dataset.id
                )
            )
            or 0
        ) + 1
        quality_value = manifest.get("quality")
        quality: Mapping[str, Any] = quality_value if isinstance(quality_value, Mapping) else {}
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_seq=next_sequence,
            version_key=manifest_artifact.sha256,
            status="candidate",
            schema_version=str(manifest["schema_version"]),
            normalize_version=str(manifest["normalize_version"]),
            schema_sha256=str(manifest["schema_sha256"]),
            adjust_type=str(manifest["adjust_type"]),
            quality_policy_version=str(quality.get("policy")) if quality.get("policy") else None,
            quality_status=str(quality.get("status") or "unknown"),
            row_count=int(manifest["row_count"]),
            min_trade_date=_parse_date(manifest.get("min_trade_date")),
            max_trade_date=_parse_date(manifest.get("max_trade_date")),
            manifest_uri=manifest_artifact.relative_uri,
            manifest_sha256=manifest_artifact.sha256,
        )
        version.partitions = [_partition_from_manifest(partition) for partition in manifest["partitions"]]
        self.db.add(version)
        try:
            with self.db.begin_nested():
                self.db.flush()
        except IntegrityError:
            existing = self.db.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.dataset_id == dataset.id,
                    DatasetVersion.manifest_sha256 == manifest_artifact.sha256,
                )
            )
            if existing is not None:
                return existing, False
            raise
        return version, True


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _partition_from_manifest(partition: Mapping[str, Any]) -> DatasetVersionPartition:
    return DatasetVersionPartition(
        partition_spec_json=dict(partition.get("key") or {}),
        relative_uri=str(partition["uri"]),
        sha256=str(partition["sha256"]),
        byte_size=int(partition["byte_size"]),
        row_count=int(partition["row_count"]),
        min_trade_date=_parse_date(partition.get("min_trade_date")),
        max_trade_date=_parse_date(partition.get("max_trade_date")),
        status="sealed",
    )
