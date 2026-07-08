"""
Phase 1: 全量拉取 A 股日K线数据到 raw 层。

策略（吸收 Qlib 思想）：
  1. baostock 全局 session（login 一次，复用）
  2. 逐只串行 fetch（不并发，避免 API 限流）
  3. 每只股票存独立 raw/{symbol}.parquet（简单追加去重）
  4. 失败收集 → 批量重试，最多 3 轮
  5. 断点续传（checkpoint JSON，每 100 只存一次）

用法：
  quant/.venv/Scripts/python.exe scripts/ops/fetch_daily_bars.py
  quant/.venv/Scripts/python.exe scripts/ops/fetch_daily_bars.py --max-retry 5 --workers 1

输出：storage/raw/daily_bars/stock_{symbol}.parquet
"""
import json
import sys
import time
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, ".")

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.db.session import get_engine, SessionLocal
from backend.app.repositories.stocks import StockRepository
from backend.app.adapters.registry import default_adapter_registry
from backend.app.adapters.baostock import (
    _to_baostock_code,
    _result_set_to_records,
)


def _coerce_date(value) -> date:
    """Convert string/date to date object"""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def get_exchange(symbol: str) -> str:
    if symbol.startswith("0") or symbol.startswith("3"):
        return "SZSE"
    return "SSE"  # 6开头=上交所主板, 68开头=科创板, 92开头=北交所(baostock用sh前缀)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch")

START = date(2022, 7, 1)
END = date.today()
RAW_DIR = Path("storage/raw/daily_bars")
CHECKPOINT_FILE = RAW_DIR.parent / ".fetch_checkpoint.json"
MAX_RETRY = 3  # 最多重试轮数
RETRY_SLEEP = 5  # 每轮重试间隔秒数
CHECKPOINT_INTERVAL = 100  # 每 N 只存一次断点

# Raw 层 schema（与 silver 一致，但不含 ingested_at 等衍生字段）
RAW_SCHEMA = pa.schema([
    pa.field("symbol", pa.string()),
    pa.field("exchange", pa.string()),
    pa.field("market", pa.string()),
    pa.field("trade_date", pa.date32()),
    pa.field("open", pa.float64()),
    pa.field("high", pa.float64()),
    pa.field("low", pa.float64()),
    pa.field("close", pa.float64()),
    pa.field("pre_close", pa.float64()),
    pa.field("volume", pa.float64()),
    pa.field("amount", pa.float64()),
    pa.field("adjust_factor", pa.float64()),
    pa.field("adjust_type", pa.string()),
    pa.field("source", pa.string()),
])


def get_exchange(symbol: str) -> str:
    if symbol.startswith("6") or symbol.startswith("68"):
        return "SSE"
    if symbol.startswith("0") or symbol.startswith("3"):
        return "SZSE"
    return "SSE"


def get_bs_symbol(symbol: str, exchange: str) -> str:
    """Convert to baostock format: sh.600519 or sz.000001"""
    prefix = "sh" if exchange == "SSE" else "sz"
    return f"{prefix}.{symbol}"


def load_checkpoint() -> dict:
    """加载断点：已完成列表、已重试列表"""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed": [], "retried": [], "last_index": 0}


def save_checkpoint(state: dict):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(state, f)


def append_to_raw(symbol: str, exchange: str, records: list) -> int:
    """追加写入 raw/{symbol}.parquet，自动去重"""
    if not records:
        return 0

    # NormalizedDailyBar → dict
    rows = []
    for r in records:
        d = asdict(r) if hasattr(r, 'trade_date') else r
        trade_date_val = d.get("trade_date") or d.get("date")
        rows.append({
            "symbol": symbol,
            "exchange": exchange,
            "market": "A_SHARE",
            "trade_date": _coerce_date(trade_date_val),
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "pre_close": float(d["pre_close"]) if d.get("pre_close") else None,
            "volume": float(d.get("volume", 0) or 0),
            "amount": float(d.get("amount", 0) or 0),
            "adjust_factor": float(d.get("adjust_factor", 1.0) or 1.0),
            "adjust_type": d.get("adjust_type", "none") or "none",
            "source": d.get("source", "baostock") or "baostock",
        })

    file_path = RAW_DIR / f"stock_{symbol}.parquet"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if file_path.exists():
        existing = pq.read_table(file_path).to_pylist()

    # 去重 (symbol, trade_date)
    seen = {(e["symbol"], str(e["trade_date"])) for e in existing}
    new_rows = [r for r in rows if (r["symbol"], str(r["trade_date"])) not in seen]
    if not new_rows:
        return 0

    table = pa.Table.from_pylist(existing + new_rows, schema=RAW_SCHEMA)
    table = table.sort_by([("symbol", "ascending"), ("trade_date", "ascending")])
    pq.write_table(table, file_path)
    return len(new_rows)


def fetch_and_save(symbol: str, bs_client, adapter) -> int:
    """拉取单只股票日线，写入 raw/，返回新增条数"""
    exchange = get_exchange(symbol)
    bs_code = _to_baostock_code(symbol, exchange)

    rs = bs_client.query_history_k_data_plus(
        bs_code,
        "date,code,open,high,low,close,preclose,volume,amount,adjustflag",
        start_date=START.isoformat(),
        end_date=END.isoformat(),
        frequency="d",
        adjustflag="3",
    )
    if rs.error_code != "0":
        raise RuntimeError(f"baostock error: {rs.error_msg}")

    raw = _result_set_to_records(rs)
    if not raw:
        return 0

    # 用 baostock adapter normalize 成统一格式
    norm = adapter.normalize_daily_bars(raw)
    return append_to_raw(symbol, exchange, norm)


def fetch_batch(symbols: list[str], bs_client, *, adapter, start_index: int = 0,
                completed: set = None) -> tuple[list[str], int]:
    """逐只串行拉取，返回失败的 symbol 列表和最后处理的 index"""
    if completed is None:
        completed = set()
    failed = []

    for idx, sym in enumerate(symbols):
        abs_idx = start_index + idx
        if sym in completed:
            continue

        t1 = time.time()
        try:
            n = fetch_and_save(sym, bs_client, adapter)
            log.info("  %d/%d %s: %d 条 (%.1fs)",
                     abs_idx + 1, len(symbols) + start_index, sym, n, time.time() - t1)
        except Exception as e:
            log.warning("  %d/%d %s 失败: %s", abs_idx + 1, len(symbols) + start_index, sym, e)
            failed.append(sym)
            continue

        # 定期保存 checkpoint
        if (abs_idx + 1) % CHECKPOINT_INTERVAL == 0:
            completed.add(sym)
            save_checkpoint({
                "completed": list(completed - {s for s in failed}),
                "retried": failed,
                "last_index": abs_idx + 1,
            })

    return failed, abs_idx + 1


def main(max_retry: int = MAX_RETRY):
    t0 = time.time()
    log.info("=" * 50)
    log.info("Phase 1: 全量拉取 A 股日K线数据")
    log.info("  日期范围: %s ~ %s", START, END)
    log.info("  raw 目录: %s", RAW_DIR.resolve())

    # 1. 获取股票列表
    log.info("获取 A 股上市股票列表...")
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    db = SessionLocal()
    stocks = StockRepository(db).list_market_stocks(
        market="A_SHARE", status="LISTED", common_only=True
    )
    db.close()
    seen = set()
    symbols = []
    for s in stocks:
        if s.symbol not in seen:
            seen.add(s.symbol)
            symbols.append(s.symbol)
    total = len(symbols)
    log.info("共 %d 只", total)

    # 2. 加载断点
    ckpt = load_checkpoint()
    completed = set(ckpt.get("completed", []))
    retried_before = set(ckpt.get("retried", []))
    last_index = ckpt.get("last_index", 0)

    log.info("断点: 已完成 %d 只, 上次处理到 #%d", len(completed), last_index)

    # 3. 排除已完成的，从断点继续
    remaining = [s for s in symbols[last_index:] if s not in completed]

    # 配置适配器
    adapter = default_adapter_registry().get("baostock")

    if not remaining and last_index >= total:
        log.info("全部已完成，跳过拉取阶段")
    else:
        # 4. 登录 baostock（全局 session，只用一次）
        import importlib
        bs = importlib.import_module("baostock")
        login_r = bs.login()
        if login_r.error_code != "0":
            log.error("baostock 登录失败: %s", login_r.error_msg)
            sys.exit(1)
        log.info("baostock 登录成功")

        try:
            # 5. 首次拉取
            log.info("开始拉取 %d 只剩余股票...", len(remaining))
            failed, processed = fetch_batch(remaining, bs, adapter=adapter, start_index=last_index, completed=completed)
            completed.update(s for s in remaining if s not in failed)

            # 6. 批量重试（最多 max_retry 轮）
            for retry_round in range(max_retry):
                if not failed:
                    break
                log.info("=== 第 %d 轮重试: %d 只 ===", retry_round + 1, len(failed))
                time.sleep(RETRY_SLEEP)
                still_failed, _ = fetch_batch(failed, bs, adapter=adapter, start_index=0)
                completed.update(s for s in failed if s not in still_failed)
                failed = still_failed

            if failed:
                log.warning("最终仍有 %d 只失败: %s", len(failed), failed[:10])

        finally:
            bs.logout()
            log.info("baostock 登出")

        # 7. 保存最终 checkpoint
        save_checkpoint({
            "completed": list(completed),
            "retried": list(failed if failed else []),
            "last_index": total,
            "elapsed_seconds": round(time.time() - t0),
        })

    # 8. 统计
    elapsed = time.time() - t0
    raw_files = list(RAW_DIR.glob("stock_*.parquet"))
    total_raw_bars = sum(pq.read_metadata(f).num_rows for f in raw_files) if raw_files else 0
    log.info("=" * 50)
    log.info("✅ 完成!")
    log.info("  原始文件: %d 个", len(raw_files))
    log.info("  原始条数: %d", total_raw_bars)
    log.info("  耗时: %.1f 分 (%.0f 秒)", elapsed / 60, elapsed)
    log.info("  目录: %s", RAW_DIR.resolve())

    # 提示下一步
    log.info("")
    log.info("👉 下一步: 运行 merge_raw_to_silver.py 合并到 silver 层")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase 1: Fetch A-share daily bars")
    parser.add_argument("--max-retry", type=int, default=MAX_RETRY, help="Max retry rounds")
    args = parser.parse_args()
    main(max_retry=args.max_retry)
