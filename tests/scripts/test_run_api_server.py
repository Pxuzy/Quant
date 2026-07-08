from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import run_api_server as runner


@pytest.fixture
def runner_storage(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(runner, "storage_dir", lambda: tmp_path)
    monkeypatch.setattr(runner, "api_host", lambda: "127.0.0.1")
    monkeypatch.setattr(runner, "api_port", lambda: 8021)
    return tmp_path


def test_start_background_does_not_adopt_existing_healthy_server(
    monkeypatch: pytest.MonkeyPatch,
    runner_storage,
) -> None:
    runner.pid_path().write_text("123", encoding="utf-8")
    monkeypatch.setattr(runner, "api_health_state", lambda timeout_seconds=3: (True, "healthy status=200"))
    monkeypatch.setattr(runner, "is_process_running", lambda pid: pid == 123)
    monkeypatch.setattr(runner, "is_managed_api_process", lambda pid: False, raising=False)
    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("should not spawn when API is already healthy"),
    )

    assert runner.start_background() == -1
    assert not runner.pid_path().exists()


def test_stop_background_removes_non_api_stale_pid_without_taskkill(
    monkeypatch: pytest.MonkeyPatch,
    runner_storage,
) -> None:
    runner.pid_path().write_text("123", encoding="utf-8")
    monkeypatch.setattr(runner, "is_process_running", lambda pid: pid == 123)
    monkeypatch.setattr(runner, "is_pid_safe_to_stop", lambda pid: False, raising=False)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("should not taskkill a stale non-API pid"),
    )

    assert runner.stop_background() is False
    assert not runner.pid_path().exists()


def test_status_text_reports_unmanaged_listener_and_clears_stale_pid(
    monkeypatch: pytest.MonkeyPatch,
    runner_storage,
) -> None:
    runner.pid_path().write_text("123", encoding="utf-8")
    monkeypatch.setattr(runner, "api_health_state", lambda timeout_seconds=3: (True, "healthy status=200"))
    monkeypatch.setattr(runner, "is_process_running", lambda pid: False)
    monkeypatch.setattr(runner, "listening_process_id", lambda: 456, raising=False)

    assert runner.status_text() == "running pid=456 (unmanaged); healthy status=200; url=http://127.0.0.1:8021/health"
    assert not runner.pid_path().exists()
