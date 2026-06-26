"""
通过 API 批量填充 A 股日K线数据。

用法：
  # 先启动后端，然后：
  /d/anaconda/python scripts/api_seed_daily_bars.py
"""
import json
import time
import urllib.request
from datetime import date, datetime

BASE = "http://127.0.0.1:8001"
START = "2024-07-01"
END = date.today().isoformat()
CHUNK = 15  # 批大小，调大可能 API 限流


def api_get(url: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def api_post(url: str, body: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get_all_stocks() -> list:
    """获取所有 A 股代码（分页直到全量）"""
    all_items = []
    page = 1
    while True:
        url = f"{BASE}/api/stocks?market=A_SHARE&common_only=true&status=LISTED&page={page}&page_size=200"
        resp = api_get(url)
        items = resp.get("items", [])
        if not items:
            break
        all_items.extend(items)
        total = resp.get("total", 0)
        if len(all_items) >= total:
            break
        page += 1
    return all_items


def main():
    print(f"[{datetime.now():%H:%M:%S}] 获取 A 股上市股票列表...")
    stocks = get_all_stocks()
    print(f"[{datetime.now():%H:%M:%S}] 共 {len(stocks)} 只 A 股")

    # 去重 (同一 symbol 别重复)
    seen = set()
    symbols = []
    for s in stocks:
        sym = s.get("symbol", s.get("code", ""))
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)

    total = len(symbols)
    print(f"[{datetime.now():%H:%M:%S}] 去重后 {total} 只，同步 {START} ~ {END}")

    success = 0
    failed = 0
    skipped = 0

    for i in range(0, total, CHUNK):
        chunk = symbols[i:i + CHUNK]

        for sym in chunk:
            try:
                resp = api_post(f"{BASE}/api/market-data/daily-bars/sync", {
                    "symbol": sym,
                    "market": "A_SHARE",
                    "start_date": START,
                    "end_date": END,
                    "source": "auto",
                })

                status = resp.get("status", "?")
                if status == "success":
                    wr = resp.get("records_written", 0)
                    success += 1
                    if wr > 0:
                        print(f"  ✅ {sym} -> {wr}条")
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1
                    msg = resp.get("message", "")[:60]
                    print(f"  ❌ {sym} | {status} | {msg}")
            except urllib.error.HTTPError as e:
                failed += 1
                body = e.read().decode()[:60]
                print(f"  💥 {sym} | HTTP {e.code} | {body}")
            except Exception as e:
                failed += 1
                print(f"  💥 {sym} | {type(e).__name__}: {str(e)[:80]}")

        if i + CHUNK < total:
            pct = min((i + CHUNK) / total * 100, 100)
            print(f"  [{datetime.now():%H:%M:%S}] {min(i+CHUNK, total)}/{total} ({pct:.0f}%) "
                  f"✅{success} ❌{failed} ⏭️{skipped} | sleep 3s")
            time.sleep(3)

    print(f"\n{'='*50}")
    print(f"  A 股日K线同步完成")
    print(f"  ✅ 成功: {success}")
    print(f"  ⏭️ 跳过: {skipped}")
    print(f"  ❌ 失败: {failed}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
