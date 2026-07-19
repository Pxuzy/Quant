from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings


@dataclass(frozen=True)
class RawArtifactMetadata:
    uri: str
    sha256: str
    byte_size: int
    row_count: int
    adjust_type: str | None = None
    content_type: str = "application/json"


class RawArtifactStore:
    """Persist and read immutable provider response envelopes.

    The store intentionally knows nothing about SQLAlchemy or provider clients.
    Database repositories can record the returned metadata after the file has
    been durably written.  The envelope is deterministic so the same task,
    source and payload produces the same checksum and artifact path.
    """

    def __init__(self, lake_root: str | Path | None = None) -> None:
        self.lake_root = Path(lake_root or get_settings().data_lake_dir)
        self.raw_root = (self.lake_root / "raw").resolve()

    def resolve_uri(self, uri: str | Path) -> Path:
        candidate = Path(uri)
        if not candidate.is_absolute():
            candidate = self.raw_root / candidate
        resolved = candidate.resolve(strict=True)
        if self.raw_root not in resolved.parents:
            raise ValueError(f"Raw artifact URI escapes configured raw root: {uri}")
        if any(parent.is_symlink() for parent in [candidate, *candidate.parents]):
            raise ValueError(f"Raw artifact URI cannot use symlinks: {uri}")
        return resolved

    def persist(
        self,
        *,
        task_id: int,
        dataset_name: str,
        source: str,
        requested_source: str,
        market: str | None,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        adjust_type: str | None = None,
        records: list[dict[str, Any]],
    ) -> RawArtifactMetadata:
        envelope = {
            "format": "quant.raw-artifact",
            "version": "v1",
            "dataset_name": dataset_name,
            "task_id": task_id,
            "source": source,
            "requested_source": requested_source,
            "market": market,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "adjust_type": adjust_type,
            "row_count": len(records),
            "records": records,
        }
        content = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        safe_dataset = _safe_component(dataset_name)
        safe_source = _safe_component(source)
        safe_symbol = _safe_component(symbol or "market")
        directory = (self.lake_root / "raw" / safe_dataset / f"source={safe_source}" / f"task={task_id}").resolve()
        path = directory / f"symbol={safe_symbol}-{digest[:16]}.json"
        directory.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            fd, temp_name = tempfile.mkstemp(prefix=".raw-", suffix=".tmp", dir=directory)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

        return RawArtifactMetadata(
            uri=str(path),
            sha256=digest,
            byte_size=len(content),
            row_count=len(records),
            adjust_type=adjust_type,
        )

    @staticmethod
    def read(uri: str | Path) -> dict[str, Any]:
        path = Path(uri)
        with path.open("r", encoding="utf-8") as handle:
            envelope = json.load(handle)
        if envelope.get("format") != "quant.raw-artifact" or envelope.get("version") != "v1":
            raise ValueError(f"Unsupported raw artifact format: {path}")
        if not isinstance(envelope.get("records"), list):
            raise ValueError(f"Raw artifact records must be a list: {path}")
        return envelope


def _safe_component(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value) or "unknown"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
