"""
快速并行填充 A 股全部股票历史日K线数据（后台运行版）。

策略：
  1. 串行 fetch（baostock 优先，全局 session 复用避免 login/logout 开销）
  2. 跳过 DB sync task 管道，直接写 Parquet
  3. 每 30 只 flush 一次，输出到日志文件

用法：
  cd /e/hermes/workspace/Quant
  python scripts/ops/seed_all_daily_bars.py 2>&1 | tee data/seed_log.txt
"""
import sys
import time
import logging
from datetime import date, datetime

sys.path.insert(0, ".")

from apps.api.adapters.base import NormalizedDailyBar
from apps.api.adapters.registry import default_adapter_registry
from apps.api.db.session import SessionLocal, get_engine
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.repositories.stocks import StockRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed")

START = date(2022, 7, 1)
END = date.today()
FLUSH_EVERY = 30
FETCH_TIMEOUT = 60


def get_exchange(symbol: str) -> str:
    if symbol.startswith("6") or symbol.startswith("68"):
        return "SSE"
    if symbol.startswith("0") or symbol.startswith("3"):
        return "SZSE"
    if symbol.startswith("11") or symbol.startswith("13"):
        return "BSE"
    return "SSE"


def main():
    t0 = time.time()
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    db = SessionLocal()

    log.info("获取 A 股上市股票列表...")
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
    log.info("共 %d 只，开始同步 %s ~ %s", total, START, END)

    # 适配器：baostock 优先，aksare 退路
    registry = default_adapter_registry()
    bs_adapter = registry.get("baostock")
    ak_adapter = registry.get("akshare")
    log.info("适配器: %s (fallback: akshare)", bs_adapter.code if bs_adapter else "akshare")

    # Baostock 全局复用 session（手动 login，避免每次 fetch 都 login/logout）
    bs = None
    if bs_adapter:
        import importlib
        bs_client = importlib.import_module("baostock")
        login_result = bs_client.login()
        if getattr(login_result, "error_code", "0") != "0":
            log.warning("baostock login 失败: %s, 回退无 session", getattr(login_result, "error_msg", "?"))
        else:
            bs = bs_client
            log.info("baostock 全局登录成功")

    repo = DailyBarRepository()
    success = failed = skipped = total_bars = 0
    buffer: list[NormalizedDailyBar] = []

    def do_fetch(sym: str) -> tuple[str, list[NormalizedDailyBar], str | None]:
        """串行 fetch，baostock 优先，复用全局 session。"""
        exchange = get_exchange(sym)
        # 第一优先：全局 baostock session（login 一次，很快）
        if bs is not None:
            try:
                from apps.api.adapters.baostock import _to_baostock_code, _result_set_to_records
                rs = bs.query_history_k_data_plus(
                    _to_baostock_code(sym, exchange),
                    "date,code,open,high,low,close,preclose,volume,amount,adjustflag",
                    start_date=START.isoformat(),
                    end_date=END.isoformat(),
                    frequency="d",
                    adjustflag="3",
                )
                if getattr(rs, "error_code", "0") == "0":
                    raw = _result_set_to_records(rs)
                    if raw:
                        norm = bs_adapter.normalize_daily_bars(raw)
                        return sym, norm, None
            except Exception as e:
                log.debug("baostock session fetch %s 失败: %s", sym, e)

        # 退路：标准适配器流程（akshare，含重试）
        for attempt in range(2):
            for adp in [ak_adapter] if ak_adapter else []:
                try:
                    bars = adp.fetch_daily_bars(
                        symbol=sym, exchange=exchange, market="A_SHARE",
                        start_date=START, end_date=END,
                    )
                    if bars:
                        norm = adp.normalize_daily_bars(bars)
                        return sym, norm, None
                except Exception:
                    continue
            if attempt == 0:
                time.sleep(2)
        return sym, [], "all_failed"

    for idx, sym in enumerate(symbols, 1):
        t1 = time.time()
        sym_out, bars, err = do_fetch(sym)
        elapsed = time.time() - t1

        if err:
            failed += 1
        elif not bars:
            skipped += 1
        else:
            success += 1
            total_bars += len(bars)
            buffer.extend(bars)

        if len(buffer) >= FLUSH_EVERY:
            if buffer:
                repo.write_many(buffer)
                buffer.clear()

        # 每 50 只打印一次进度
        if idx % 50 == 0 or idx == total:
            if buffer:
                repo.write_many(buffer)
                buffer.clear()
            elapsed_t = time.time() - t0
            rate = idx / elapsed_t * 60 if elapsed_t > 0 else 0
            eta = (total - idx) / rate * 60 if rate > 0 else 0
            log.info("%d/%d (%.0f%%) ✅%d ❌%d ⏭️%d | %d条 | %.0f只/分 | ETA %.0f分",
                     idx, total, idx/total*100, success, failed, skipped,
                     total_bars, rate, eta/60)
        elif idx % 10 == 0:
            log.info("  %d/%d %s: %d条 (%.1fs)", idx, total, sym_out, len(bars) if bars else 0, elapsed)

    # 最后 flush
    if buffer:
        repo.write_many(buffer)

    # 登出 baostock
    if bs is not None:
        try:
            bs.logout()
            log.info("baostock 登出")
        except Exception:
            pass

    elapsed = time.time() - t0
    log.info("=" * 50)
    log.info("完成!")
    log.info("📅 %s ~ %s (%d 年)", START, END, END.year - START.year)
    log.info("✅ 成功: %d 只, %d 条", success, total_bars)
    log.info("⏭️ 跳过: %d 只", skipped)
    log.info("❌ 失败: %d 只", failed)
    log.info("⏱  耗时: %.1f 分", elapsed / 60)


if __name__ == "__main__":
    main()
