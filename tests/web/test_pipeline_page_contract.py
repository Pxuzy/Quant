from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def test_pipeline_page_uses_governed_sync_task_apis():
    source = (ROOT_DIR / "frontend/src/pages/data-system/pipeline/PipelinePage.tsx").read_text(encoding="utf-8")

    assert "/api/data-pipeline" not in source
    assert "useSyncRunnerStatusQuery" in source
    assert "useSyncTasksQuery" in source
