"""批量拉取复权数据：按 adjust_type 分批处理，直到所有股票补全。"""
import subprocess, sys, time, os

ADJUST_TYPES = ["none", "qfq", "hfq"]
BATCH_SIZE = 20        # 小批次，避免触发腾讯/AKShare限速
BATCH_TIMEOUT = 300
MAX_EMPTY_RUNS = 3

base_cmd = [
    sys.executable, "-m", "backend.worker.sync_stocks",
    "--task-type", "daily_bars_market_repair",
    "--source", "akshare",           # 暂用 AKShare
    "--start-date", "2026-06-01",
    "--end-date", "2026-07-22",
    "--start-policy", "requested_start",
]

# 避免代理干扰东方财富 API
env = {
    **os.environ,
    "QUANT_REPAIR_PARALLELISM": "3",
    "NO_PROXY": "push2his.eastmoney.com,*.eastmoney.com,123.126.*",
    "no_proxy": "push2his.eastmoney.com,*.eastmoney.com,123.126.*",
}

for adj in ADJUST_TYPES:
    print(f"\n{'='*50}")
    print(f"▶  开始拉取 {adj} 数据")
    print(f"{'='*50}")
    empty_runs = 0

    while empty_runs < MAX_EMPTY_RUNS:
        cmd = base_cmd + ["--adjust-type", adj, "--max-symbols", str(BATCH_SIZE)]
        print(f"  运行: {adj} batch (BATCH_SIZE={BATCH_SIZE})...", flush=True)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=BATCH_TIMEOUT, env=env)
        except subprocess.TimeoutExpired as exc:
            print(f"  ⚠ 超时: {adj} batch after {BATCH_TIMEOUT}s; 保留任务状态，稍后重试", flush=True)
            empty_runs += 1
            time.sleep(5)
            continue
        out = result.stdout.strip()
        err = result.stderr.strip()

        if result.returncode == 0 and out:
            print(f"  → {out[-120:]}")
            # 检查是否有写入
            if '"records_written": 0' in out and '"partial_success"' not in out:
                empty_runs += 1
                print(f"  ⚠ 空批次 ({empty_runs}/{MAX_EMPTY_RUNS})")
            else:
                empty_runs = 0  # 有数据就重置计数
        else:
            print(f"  ⚠ 异常: rc={result.returncode} err={err[:200]}")
            empty_runs += 1

        if empty_runs >= MAX_EMPTY_RUNS:
            print(f"  ✅ {adj} 拉取完毕（连续 {MAX_EMPTY_RUNS} 次空跑）")
            break

        time.sleep(2)  # 批次间隔

print(f"\n{'='*50}")
print("✅ 全部复权数据拉取完成")
print(f"{'='*50}")
