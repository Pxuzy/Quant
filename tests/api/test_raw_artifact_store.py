from __future__ import annotations

import hashlib
import json
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
