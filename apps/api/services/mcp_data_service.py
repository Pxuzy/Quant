"""
MCP cache read/write tools — provides JSON cache I/O for FastAPI routes and MCP data bridging.
Actual MCP calls are done by Hermes cron job via agent tools, not Python import.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(r"E:\hermes\workspace\Quant\data\mcp_cache")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 缓存文件路径 ──
INDUSTRY_FLOW_FILE = DATA_DIR / "industry_flow.json"
CONCEPT_FLOW_FILE = DATA_DIR / "concept_flow.json"
MAIN_FUND_FILE = DATA_DIR / "main_fund_rank.json"
NORTHBOUND_FILE = DATA_DIR / "northbound_flow.json"
THS_SECTOR_MAP_FILE = DATA_DIR / "ths_sector_map.json"

# ── 读写 API ──

def save_json(path: Path, data: Any) -> None:
    """写入 JSON 缓存"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: Path) -> list[dict] | dict | None:
    """读取 JSON 缓存"""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读 {path.name} 失败: {e}")
    return None


def _data_items(data: Any) -> Any:
    """统一从 {data: ...} 或裸 list 中提取数据"""
    return data.get("data", data) if isinstance(data, dict) else data


# ── 快捷读取函数（API 路由直接调用） ──

def get_industry_flow(limit: int = 20) -> list[dict]:
    data = load_json(INDUSTRY_FLOW_FILE)
    return _data_items(data)[:limit] if data else []


def get_concept_flow(limit: int = 20) -> list[dict]:
    data = load_json(CONCEPT_FLOW_FILE)
    return _data_items(data)[:limit] if data else []


def get_main_fund_rank(limit: int = 20) -> list[dict]:
    data = load_json(MAIN_FUND_FILE)
    return _data_items(data)[:limit] if data else []


def get_northbound_flow() -> dict:
    data = load_json(NORTHBOUND_FILE)
    return _data_items(data) if isinstance(data, dict) and data else {}


def get_all_keys() -> list[str]:
    """列出所有缓存文件名（不含扩展名）"""
    return [f.stem for f in DATA_DIR.glob("*.json")]


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print(f"MCP cache dir: {DATA_DIR}")
    for f in sorted(DATA_DIR.glob("*.json")):
        size = f.stat().st_size
        print(f"  {f.name}: {size/1024:.1f} KB")
