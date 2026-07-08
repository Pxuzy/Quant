"""
Batch fetch worker — runs in a subprocess to isolate baostock GIL crashes.
Usage: python batch_fetch_worker.py <symbols_json> <start_date> <end_date>
"""
import sys
import json
import time
import logging
from pathlib import Path
from datetime import date

sys.path.insert(0, ".")

import pyarrow.parquet as pq
import pyarrow as pa
import importlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch-worker")

RAW_DIR = Path("storage/raw/daily_bars")


def get_exchange(symbol: str) -> str:
    if symbol.startswith("0") or symbol.startswith("3"):
        return "SZSE"
    return "SSE"  # 6=主板, 68=科创板, 92=北交所(baostock用sh前缀)


def main():
    symbols_file = Path(sys.argv[1])
    start_date = sys.argv[2]
    end_date = sys.argv[3]
    batch_size = int(sys.argv[4]) if len(sys.argv) > 4 else 50

    with open(symbols_file) as f:
        symbols = json.load(f)

    from backend.app.adapters.baostock import _to_baostock_code, _result_set_to_records
    bs = importlib.import_module("baostock")
    bs.login()

    success = failed = total_bars = 0

    try:
        for idx, sym in enumerate(symbols, 1):
            if idx > 1 and idx % batch_size == 0:
                bs.logout()
                time.sleep(0.5)
                bs.login()

            exchange = get_exchange(sym)
            try:
                rs = bs.query_history_k_data_plus(
                    _to_baostock_code(sym, exchange),
                    "date,code,open,high,low,close,preclose,volume,amount,adjustflag",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3",
                )
                if rs.error_code != "0":
                    failed += 1
                    continue

                raw = _result_set_to_records(rs)
                if not raw:
                    continue

                rows = [{
                    "symbol": sym, "exchange": exchange, "market": "A_SHARE",
                    "trade_date": r["date"],
                    "open": float(r["open"]), "high": float(r["high"]),
                    "low": float(r["low"]), "close": float(r["close"]),
                    "pre_close": float(r.get("preclose", 0) or 0),
                    "volume": float(r.get("volume", 0) or 0),
                    "amount": float(r.get("amount", 0) or 0),
                    "adjust_factor": 1.0, "adjust_type": "none", "source": "baostock",
                } for r in raw]

                f_out = RAW_DIR / f"stock_{sym}.parquet"
                existing = pq.read_table(f_out).to_pylist() if f_out.exists() else []
                seen_keys = {(e["symbol"], str(e["trade_date"])) for e in existing}
                new_rows = [r for r in rows if (r["symbol"], str(r["trade_date"])) not in seen_keys]

                if new_rows:
                    table = pa.Table.from_pylist(existing + new_rows)
                    table = table.sort_by([("symbol", "ascending"), ("trade_date", "ascending")])
                    pq.write_table(table, f_out)

                total_bars += len(new_rows)
                success += 1

            except Exception as e:
                failed += 1
    finally:
        bs.logout()

    log.info("RESULT: success=%d failed=%d bars=%d", success, failed, total_bars)
    print(f"RESULT:{success}:{failed}:{total_bars}")


if __name__ == "__main__":
    main()
