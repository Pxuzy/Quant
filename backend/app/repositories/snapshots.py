from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetVersion, Snapshot, SnapshotMember
from backend.app.models.entities import utcnow


class SnapshotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_draft(self, *, name: str) -> Snapshot:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("snapshot name must not be empty")
        snapshot = Snapshot(name=normalized_name, status="draft")
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def add_member(
        self,
        snapshot: Snapshot,
        *,
        dataset: Dataset,
        version: DatasetVersion,
        role: str,
    ) -> SnapshotMember:
        if snapshot.status != "draft":
            raise ValueError(f"only draft snapshots can be modified; current status={snapshot.status}")
        if version.status != "published":
            raise ValueError("snapshot members must reference published dataset versions")
        if version.dataset_id != dataset.id:
            raise ValueError("snapshot member dataset and version do not match")
        normalized_role = role.strip()
        if not normalized_role:
            raise ValueError("snapshot member role must not be empty")
        expected_adjust_type = {
            "bars-none": "none",
            "bars-qfq": "qfq",
            "bars-hfq": "hfq",
        }.get(normalized_role)
        if expected_adjust_type is not None and version.adjust_type != expected_adjust_type:
            raise ValueError(
                f"snapshot role {normalized_role} requires adjust_type={expected_adjust_type}"
            )
        member = SnapshotMember(
            snapshot_id=snapshot.id,
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            role=normalized_role,
        )
        self.db.add(member)
        self.db.flush()
        return member

    def activate(self, snapshot: Snapshot) -> Snapshot:
        if snapshot.status != "draft":
            raise ValueError(f"only draft snapshots can be activated; current status={snapshot.status}")
        if not snapshot.members:
            raise ValueError("snapshot must contain at least one member before activation")
        if any(member.dataset_version.status != "published" for member in snapshot.members):
            raise ValueError("snapshot members must reference published dataset versions")

        active_snapshots = self.db.scalars(
            select(Snapshot).where(Snapshot.status == "active").with_for_update()
        ).all()
        now = utcnow()
        for active_snapshot in active_snapshots:
            active_snapshot.status = "retired"
            active_snapshot.retired_at = now
        snapshot.status = "active"
        snapshot.activated_at = now
        self.db.flush()
        return snapshot

    def count_active(self) -> int:
        return int(
            self.db.scalar(select(func.count(Snapshot.id)).where(Snapshot.status == "active")) or 0
        )
