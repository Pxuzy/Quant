from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_VOLATILE_FIELDS = {"created_at", "generated_at"}
_REQUIRED_FIELDS = {
    "manifest_version",
    "dataset",
    "dataset_version_id",
    "schema_version",
    "normalize_version",
    "schema_sha256",
    "adjust_type",
    "row_count",
    "partitions",
}


class ManifestValidationError(ValueError):
    """Raised when a manifest cannot safely identify immutable data."""


@dataclass(frozen=True)
class ManifestArtifact:
    relative_uri: str
    sha256: str
    byte_size: int


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported manifest value: {type(value).__name__}")


def _canonical_document(manifest: Mapping[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(dict(manifest))
    for field in _VOLATILE_FIELDS:
        document.pop(field, None)
    return document


def canonical_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Serialize semantic manifest content deterministically, excluding timestamps."""
    return json.dumps(
        _canonical_document(manifest),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
    ).encode("utf-8")


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _require_non_empty_string(manifest: Mapping[str, Any], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"manifest field '{field}' must be a non-empty string")
    return value.strip()


def _validate_date(value: Any, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ManifestValidationError(f"manifest field '{field}' must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ManifestValidationError(f"manifest field '{field}' must be an ISO date") from exc


def _validate_relative_uri(uri: Any) -> str:
    if not isinstance(uri, str) or not uri.strip():
        raise ManifestValidationError("partition relative URI must be a non-empty string")
    value = uri.strip()
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ntpath.isabs(value)
        or "\\" in value
        or ".." in path.parts
        or "://" in value
    ):
        raise ManifestValidationError("partition URI must be a relative URI without path escape")
    return value


def _validate_component(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise ManifestValidationError(f"manifest field '{field}' contains an unsafe path component")
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the structural and integrity invariants of a canonical manifest."""
    if not isinstance(manifest, Mapping):
        raise ManifestValidationError("manifest must be a mapping")

    missing = sorted(_REQUIRED_FIELDS - manifest.keys())
    if missing:
        raise ManifestValidationError(f"manifest is missing required fields: {', '.join(missing)}")

    _require_non_empty_string(manifest, "manifest_version")
    _validate_component(_require_non_empty_string(manifest, "dataset"), "dataset")
    _validate_component(_require_non_empty_string(manifest, "dataset_version_id"), "dataset_version_id")
    _require_non_empty_string(manifest, "schema_version")
    _require_non_empty_string(manifest, "normalize_version")
    _require_non_empty_string(manifest, "adjust_type")

    schema_sha256 = _require_non_empty_string(manifest, "schema_sha256")
    if not _HEX_SHA256.fullmatch(schema_sha256):
        raise ManifestValidationError("schema_sha256 must be a lowercase SHA-256 hex digest")

    row_count = manifest.get("row_count")
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise ManifestValidationError("manifest row_count must be a non-negative integer")

    _validate_date(manifest.get("min_trade_date"), "min_trade_date")
    _validate_date(manifest.get("max_trade_date"), "max_trade_date")
    if manifest.get("min_trade_date") and manifest.get("max_trade_date"):
        if manifest["min_trade_date"] > manifest["max_trade_date"]:
            raise ManifestValidationError("manifest min_trade_date cannot exceed max_trade_date")

    partitions = manifest.get("partitions")
    if not isinstance(partitions, list):
        raise ManifestValidationError("manifest partitions must be a list")

    seen_uris: set[str] = set()
    partition_rows = 0
    for partition in partitions:
        if not isinstance(partition, Mapping):
            raise ManifestValidationError("each manifest partition must be a mapping")
        uri = _validate_relative_uri(partition.get("uri"))
        if uri in seen_uris:
            raise ManifestValidationError(f"duplicate partition URI: {uri}")
        seen_uris.add(uri)

        checksum = partition.get("sha256")
        if not isinstance(checksum, str) or not _HEX_SHA256.fullmatch(checksum):
            raise ManifestValidationError(f"partition '{uri}' sha256 must be a lowercase SHA-256 hex digest")
        byte_size = partition.get("byte_size")
        if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size < 0:
            raise ManifestValidationError(f"partition '{uri}' byte_size must be a non-negative integer")
        partition_row_count = partition.get("row_count")
        if (
            not isinstance(partition_row_count, int)
            or isinstance(partition_row_count, bool)
            or partition_row_count < 0
        ):
            raise ManifestValidationError(f"partition '{uri}' row_count must be a non-negative integer")
        partition_rows += partition_row_count
        _validate_date(partition.get("min_trade_date"), f"partition '{uri}' min_trade_date")
        _validate_date(partition.get("max_trade_date"), f"partition '{uri}' max_trade_date")

    if partition_rows != row_count:
        raise ManifestValidationError(
            f"manifest row_count {row_count} does not equal partition row_count sum {partition_rows}"
        )


def _manifest_relative_uri(manifest: Mapping[str, Any], digest: str) -> str:
    dataset = _validate_component(_require_non_empty_string(manifest, "dataset"), "dataset")
    return f"versions/{dataset}/manifest-{digest}.json"


class DatasetManifestStore:
    """Persist canonical manifests below a controlled data-lake root."""

    def __init__(self, lake_root: str | Path) -> None:
        self.lake_root = Path(lake_root).expanduser().resolve()

    def write(self, manifest: Mapping[str, Any]) -> ManifestArtifact:
        validate_manifest(manifest)
        payload = canonical_manifest_bytes(manifest)
        digest = hashlib.sha256(payload).hexdigest()
        relative_uri = _manifest_relative_uri(manifest, digest)
        target = (self.lake_root / relative_uri).resolve()
        try:
            target.relative_to(self.lake_root)
        except ValueError as exc:
            raise ManifestValidationError("manifest path escapes the configured lake root") from exc

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_bytes()
            if existing != payload:
                raise ManifestValidationError("immutable manifest path already contains different bytes")
            return ManifestArtifact(relative_uri=relative_uri, sha256=digest, byte_size=len(existing))

        fd, temporary_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
            directory_fd = os.open(target.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

        return ManifestArtifact(relative_uri=relative_uri, sha256=digest, byte_size=len(payload))
