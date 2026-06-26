"""数据管线管理 API — 触发全量同步 / 增量更新 / 查看进度"""
from __future__ import annotations

import logging
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/data-pipeline", tags=["data-pipeline"])

logger = logging.getLogger("data-pipeline")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "fetch_daily_bars.py"
MERGE_SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "merge_raw_to_silver.py"
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "daily_update_bars.py"

# 运行中的进程引用
_running_jobs: dict[str, subprocess.Popen] = {}


def _run(script: Path, name: str, background: bool = True) -> dict:
    """启动脚本进程"""
    if name in _running_jobs and _running_jobs[name].poll() is None:
        return {"status": "running", "message": f"{name} 已在运行中 (PID {_running_jobs[name].pid})"}

    proc = subprocess.Popen(
        [sys.executable, "-u", str(script)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE if background else None,
        stderr=subprocess.STDOUT if background else None,
        text=True,
    )
    _running_jobs[name] = proc

    if background:
        return {"status": "started", "job": name, "pid": proc.pid, "script": script.name}
    else:
        stdout, _ = proc.communicate(timeout=60)
        return {
            "status": "completed" if proc.returncode == 0 else "failed",
            "job": name,
            "returncode": proc.returncode,
            "output": stdout[-500:] if stdout else "",
        }


@router.get("/status")
def pipeline_status() -> dict:
    """获取所有管线运行状态"""
    jobs = {}
    for name, proc in _running_jobs.items():
        jobs[name] = {
            "pid": proc.pid,
            "status": "running" if proc.poll() is None else f"exited({proc.returncode})",
        }

    # raw 状态
    raw_dir = PROJECT_ROOT / "storage" / "raw" / "daily_bars"
    raw_files = list(raw_dir.glob("stock_*.parquet")) if raw_dir.exists() else []

    return {
        "jobs": jobs,
        "raw_files": len(raw_files),
        "raw_size_mb": round(sum(f.stat().st_size for f in raw_files) / 1024 / 1024, 1),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/fetch-status")
def fetch_checkpoint_status() -> dict:
    """读取 fetch checkpoint，显示拉取进度"""
    ckpt_file = PROJECT_ROOT / "storage" / "raw" / ".fetch_checkpoint.json"
    if not ckpt_file.exists():
        return {"status": "no_checkpoint", "message": "尚未运行 fetch_daily_bars.py"}
    with open(ckpt_file) as f:
        ckpt = json.load(f)
    completed = ckpt.get("completed", [])
    retried = ckpt.get("retried", [])
    total_stocks = 5526
    pct = round(len(completed) / total_stocks * 100, 1) if total_stocks else 0
    return {
        "completed": len(completed),
        "failed": len(retried),
        "total": total_stocks,
        "progress_pct": pct,
        "last_index": ckpt.get("last_index", 0),
        "status": "finished" if ckpt.get("last_index", 0) >= total_stocks else "running",
    }


@router.post("/run-fetch")
def trigger_fetch(
    background: bool = Query(default=True, description="是否后台运行"),
    max_retry: int = Query(default=3, ge=1, le=10),
) -> dict:
    """触发全量拉取（覆盖已有数据）"""
    if not FETCH_SCRIPT.exists():
        raise HTTPException(404, f"脚本不存在：{FETCH_SCRIPT}")
    result = _run(FETCH_SCRIPT, "fetch_all", background=background)
    result["max_retry"] = max_retry
    return result


@router.post("/run-merge")
def trigger_merge(
    background: bool = Query(default=False, description="默认同步等待完成"),
) -> dict:
    """触发 raw → silver 合并"""
    if not MERGE_SCRIPT.exists():
        raise HTTPException(404, f"脚本不存在：{MERGE_SCRIPT}")
    return _run(MERGE_SCRIPT, "merge_silver", background=background)


@router.post("/run-update")
def trigger_daily_update(
    background: bool = Query(default=True, description="是否后台运行"),
) -> dict:
    """触发增量更新（只在已有数据基础上追加新数据）"""
    if not UPDATE_SCRIPT.exists():
        raise HTTPException(404, f"脚本不存在：{UPDATE_SCRIPT}")
    return _run(UPDATE_SCRIPT, "daily_update", background=background)


@router.post("/stop/{job_name}")
def stop_job(job_name: str) -> dict:
    """停止正在运行的后台 job"""
    proc = _running_jobs.get(job_name)
    if proc is None or proc.poll() is not None:
        return {"status": "not_running", "job": job_name}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return {"status": "stopped", "job": job_name}
