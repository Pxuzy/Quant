"""一次性验证所有活跃数据源"""
import json
import urllib.request

# 设置代理（Windows Clash Verge）
proxy_support = urllib.request.ProxyHandler({
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
})
opener = urllib.request.build_opener(proxy_support)
urllib.request.install_opener(opener)

BASE = "http://127.0.0.1:8001"

sources = ["akshare", "baostock", "adata"]
capabilities = ["stock_list", "daily_bars"]

results = {"passed": 0, "failed": 0}

for src in sources:
    print(f"\n{'='*40}")
    print(f"  {src}")
    print(f"{'='*40}")
    for cap in capabilities:
        url = f"{BASE}/api/data-sources/{src}/smoke-test?capability={cap}"
        try:
            req = urllib.request.Request(url, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                d = json.loads(resp.read().decode())
            if d["healthy"]:
                mark = "✅"
                results["passed"] += 1
            else:
                mark = "❌"
                results["failed"] += 1
            print(f"  {mark} {cap:15s}  {d['raw_records']:>5}条 → {d['normalized_records']:>5}条规范")
        except Exception as e:
            results["failed"] += 1
            print(f"  ❌ {cap:15s}  ERROR: {str(e)[:80]}")

print(f"\n{'='*40}")
print(f"  结果: ✅ {results['passed']} 通过, ❌ {results['failed']} 失败 / {results['passed']+results['failed']} 总计")