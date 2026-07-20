from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetVersion, DatasetVersionPartition
from backend.app.models.entities import utcnow
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
            bundle_key=str(manifest["bundle_key"]) if manifest.get("bundle_key") else None,
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

    def mark_ready(self, version: DatasetVersion) -> DatasetVersion:
        if version.status != "candidate":
            raise ValueError(f"only candidate versions can become ready; current status={version.status}")
        if version.quality_status != "good":
            raise ValueError("quality gate must pass before version becomes ready")
        if not version.partitions:
            raise ValueError("version must contain at least one partition before becoming ready")
        if any(partition.status != "sealed" for partition in version.partitions):
            raise ValueError("all version partitions must be sealed before becoming ready")
        version.status = "ready"
        self.db.flush()
        return version

    def publish(self, version: DatasetVersion) -> DatasetVersion:
        if version.status != "ready":
            raise ValueError(f"only ready versions can be published; current status={version.status}")
        version.status = "published"
        version.published_at = utcnow()
        self.db.flush()
        return version

    def reject(self, version: DatasetVersion, *, reason: str) -> DatasetVersion:
        if version.status not in {"candidate", "ready"}:
            raise ValueError(f"only candidate or ready versions can be rejected; current status={version.status}")
        if not reason.strip():
            raise ValueError("rejection reason must not be empty")
        version.status = "rejected"
        version.failure_reason = reason.strip()
        self.db.flush()
        return version


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
