from __future__ import annotations

import hashlib
import json
import os
from datetime import date

from backend.app.services.raw_artifact_store import RawArtifactStore


def test_raw_artifact_store_persists_deterministic_envelope_and_reads_it(tmp_path):
    store = RawArtifactStore(tmp_path / "lake")
    records = [
        {"trade_date": date(2026, 6, 1), "close": 10.5},
        {"trade_date": date(2026, 6, 2), "close": 11.2},
    ]

    first = store.persist(
        task_id=7,
        dataset_name="daily_bars",
        source="baostock",
        requested_source="auto",
        market="A_SHARE",
        symbol="600519",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        records=records,
    )
    second = store.persist(
        task_id=7,
        dataset_name="daily_bars",
        source="baostock",
        requested_source="auto",
        market="A_SHARE",
        symbol="600519",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        records=records,
    )

    assert first == second
    path = tmp_path / "lake" / "raw" / "daily_bars" / "source=baostock" / "task=7" / f"symbol=600519-{first.sha256[:16]}.json"
    assert path.exists()
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == first.sha256
    assert len(content) == first.byte_size

    envelope = RawArtifactStore.read(first.uri)
    assert envelope["format"] == "quant.raw-artifact"
    assert envelope["records"] == [
        {"trade_date": "2026-06-01", "close": 10.5},
        {"trade_date": "2026-06-02", "close": 11.2},
    ]
    assert json.loads(content.decode("utf-8"))["row_count"] == 2


def test_raw_artifact_store_rejects_uri_outside_configured_raw_root(tmp_path):
    lake_root = tmp_path / "lake"
    store = RawArtifactStore(lake_root)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    try:
        store.resolve_uri(outside)
    except ValueError as exc:
        assert "escapes configured raw root" in str(exc)
    else:
        raise AssertionError("Expected raw root containment rejection")


def test_raw_artifact_store_rejects_symlink_escape(tmp_path):
    lake_root = tmp_path / "lake"
    raw_dir = lake_root / "raw"
    raw_dir.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = raw_dir / "escaped.json"
    try:
        os.symlink(outside, link)
    except OSError as exc:
        if exc.errno in {1, 95}:
            return
        raise

    try:
        RawArtifactStore(lake_root).resolve_uri(link)
    except ValueError as exc:
        assert "escapes configured raw root" in str(exc) or "cannot use symlinks" in str(exc)
    else:
        raise AssertionError("Expected symlink escape rejection")
