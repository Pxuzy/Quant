from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from backend.app.repositories._base import BaseRepository

from backend.app.models import RawArtifact, SyncTask
from backend.app.services.raw_artifact_store import RawArtifactMetadata


class RawArtifactRepository(BaseRepository):

    def create_artifact(
        self,
        *,
        task: SyncTask,
        dataset_name: str,
        source: str,
        requested_source: str,
        market: str | None,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        adjust_type: str | None = None,
        metadata: RawArtifactMetadata,
    ) -> RawArtifact:
        artifact = RawArtifact(
            task_id=task.id,
            dataset_name=dataset_name,
            source=source,
            requested_source=requested_source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type or metadata.adjust_type,
            uri=metadata.uri,
            sha256=metadata.sha256,
            byte_size=metadata.byte_size,
            row_count=metadata.row_count,
            content_type=metadata.content_type,
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact
