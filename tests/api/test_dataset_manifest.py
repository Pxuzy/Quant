from __future__ import annotations

from datetime import date

import pytest

from backend.app.services.dataset_manifest import (
    DatasetManifestStore,
    ManifestValidationError,
    canonical_manifest_bytes,
    manifest_sha256,
    validate_manifest,
)


def _manifest(*, generated_at: str = "2026-07-19T00:00:00Z", row_count: int = 2) -> dict:
    return {
        "manifest_version": "v1",
        "dataset": "daily_bars",
        "dataset_version_id": "daily-bars-v1",
        "schema_version": "v1",
        "normalize_version": "v1",
        "schema_sha256": "a" * 64,
        "adjust_type": "none",
        "primary_keys": ["symbol", "exchange", "market", "trade_date", "adjust_type"],
        "partition_keys": ["market", "trade_date"],
        "row_count": row_count,
        "min_trade_date": "2026-07-18",
        "max_trade_date": "2026-07-18",
        "quality": {"status": "good", "policy": "daily-bars-v1"},
        "lineage": {"ingest_batch_ids": [1], "raw_artifact_ids": [2]},
        "generated_at": generated_at,
        "partitions": [
            {
                "key": {"market": "A_SHARE", "trade_date": "2026-07-18"},
                "uri": "versions/daily_bars/v1/market=A_SHARE/trade_date=2026-07-18/part-000.parquet",
                "sha256": "b" * 64,
                "byte_size": 100,
                "row_count": row_count,
                "min_trade_date": "2026-07-18",
                "max_trade_date": "2026-07-18",
            }
        ],
    }


def test_canonical_manifest_hash_is_stable_for_key_order_and_generation_time():
    first = _manifest(generated_at="2026-07-19T00:00:00Z")
    second = dict(reversed(list(_manifest(generated_at="2026-07-20T00:00:00Z").items())))

    assert canonical_manifest_bytes(first) == canonical_manifest_bytes(second)
    assert manifest_sha256(first) == manifest_sha256(second)


def test_validate_manifest_rejects_partition_path_escape():
    manifest = _manifest()
    manifest["partitions"][0]["uri"] = "../outside/part.parquet"

    with pytest.raises(ManifestValidationError, match="relative URI"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_absolute_partition_path():
    manifest = _manifest()
    manifest["partitions"][0]["uri"] = "/tmp/outside/part.parquet"

    with pytest.raises(ManifestValidationError, match="relative URI"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_windows_partition_path():
    manifest = _manifest()
    manifest["partitions"][0]["uri"] = r"C:\outside\part.parquet"

    with pytest.raises(ManifestValidationError, match="relative URI"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_duplicate_partition_uri():
    manifest = _manifest()
    manifest["partitions"].append(dict(manifest["partitions"][0]))
    manifest["row_count"] = 4

    with pytest.raises(ManifestValidationError, match="duplicate partition URI"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_invalid_partition_checksum():
    manifest = _manifest()
    manifest["partitions"][0]["sha256"] = "not-a-checksum"

    with pytest.raises(ManifestValidationError, match="sha256"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_invalid_partition_date():
    manifest = _manifest()
    manifest["partitions"][0]["min_trade_date"] = "2026-02-30"

    with pytest.raises(ManifestValidationError, match="ISO date"):
        validate_manifest(manifest)


def test_validate_manifest_requires_partition_counts_to_match_manifest():
    manifest = _manifest(row_count=3)
    manifest["partitions"][0]["row_count"] = 2

    with pytest.raises(ManifestValidationError, match="row_count"):
        validate_manifest(manifest)


def test_manifest_store_writes_immutable_canonical_file(tmp_path):
    store = DatasetManifestStore(tmp_path / "lake")
    manifest = _manifest()

    artifact = store.write(manifest)
    path = tmp_path / "lake" / artifact.relative_uri

    assert artifact.sha256 == manifest_sha256(manifest)
    assert artifact.byte_size == path.stat().st_size
    assert path.read_bytes() == canonical_manifest_bytes(manifest)
    assert artifact.relative_uri.startswith("versions/daily_bars/")

    second = store.write(dict(reversed(list(manifest.items()))))
    assert second == artifact
    assert path.read_bytes() == canonical_manifest_bytes(manifest)


def test_manifest_store_rejects_dataset_path_escape(tmp_path):
    manifest = _manifest()
    manifest["dataset"] = "../outside"

    with pytest.raises(ManifestValidationError, match="dataset"):
        DatasetManifestStore(tmp_path / "lake").write(manifest)
