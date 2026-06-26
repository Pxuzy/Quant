"""
财务数据拉取 — 通过 ashare-mcp 获取 A 股财报摘要
用法: python scripts/ops/fetch_fundamentals.py
"""
import sys
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fundamentals")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "mcp_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
FUNDAMENTAL_FILE = CACHE_DIR / "fundamentals.json"


def fetch_fundamentals():
    """通过 Hermes MCP ashare-mcp 获取财报数据"""
    # 使用 Hermes MCP 工具获取数据
    # 这里我们用 MCP 工具调用 ashare-mcp
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    # 调用 ashare-mcp MCP 工具
    # 注意：MCP 工具需要在 Hermes agent 上下文中调用
    # 这里我们用 subprocess 调用一个辅助脚本
    helper = PROJECT_ROOT / "scripts" / "ops" / "_fetch_fundamentals_helper.py"

    if not helper.exists():
        log.warning("Helper script not found, creating...")
        helper.write_text('''import sys, json
sys.path.insert(0, ".")
# This script is a placeholder - fundamentals are fetched via Hermes MCP cron
print("USE_MCP_CRON")
''')

    log.info("Fundamentals data is fetched via Hermes MCP cron job")
    log.info("Run: hermes run mcp_ashare_mcp_get_three_statements to update fundamentals")


if __name__ == "__main__":
    fetch_fundamentals()
