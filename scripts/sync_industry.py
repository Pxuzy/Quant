"""一次性脚本：从 Baostock 拉取全市场证监会行业分类，回写 stocks.industry。

用法：python scripts/sync_industry.py

特点：
- 1 次 API 调用拿 5500+ 只股票行业
- Baostock 免费稳定，无限速风险
- 证监会一级行业分类（A 股官方标准）
- 幂等，可重复运行
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 确保能 import backend
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import baostock as bs
import sqlite3
from datetime import datetime


DB_PATH = ROOT / "storage" / "quant.db"


def main():
    print(f"[{datetime.now():%H:%M:%S}] 登录 Baostock ...")
    lg = bs.login()
    if lg.error_code != "0":
        print(f"Baostock 登录失败: {lg.error_msg}")
        sys.exit(1)

    try:
        print(f"[{datetime.now():%H:%M:%S}] 拉取行业数据 ...")
        rs = bs.query_stock_industry()
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        print(f"  获取 {len(rows)} 条记录")

        # 解析：updateDate, code, code_name, industry, industryClassification
        # code 格式: sh.600000 → 提取 600000
        stock_industry: dict[str, str] = {}
        empty = 0
        for r in rows:
            code = r[1].split(".")[-1]  # sh.600000 → 600000
            industry = (r[3] or "").strip()
            if industry:
                stock_industry[code] = industry
            else:
                empty += 1

        print(f"  有行业: {len(stock_industry)}, 无行业: {empty}")

        print(f"[{datetime.now():%H:%M:%S}] 回写 SQLite ...")
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()

        updated = 0
        skipped = 0
        for code, industry in stock_industry.items():
            c.execute(
                "UPDATE stocks SET industry = ? WHERE symbol = ?",
                (industry, code),
            )
            if c.rowcount:
                updated += 1
            else:
                skipped += 1

        conn.commit()
        conn.close()

        print(f"  更新 {updated} 只股票, 跳过 {skipped}（不在本地股票池）")
        print(f"[{datetime.now():%H:%M:%S}] ✅ 完成")

        # 验证
        conn2 = sqlite3.connect(str(DB_PATH))
        c2 = conn2.cursor()
        total = c2.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        has_ind = c2.execute("SELECT COUNT(*) FROM stocks WHERE industry IS NOT NULL").fetchone()[0]
        print(f"\n验证: {total} 只股票, {has_ind} 只有行业分类")
        print("行业样例:")
        for r in c2.execute("SELECT DISTINCT industry FROM stocks WHERE industry IS NOT NULL ORDER BY industry LIMIT 15"):
            print(f"  - {r[0]}")
        conn2.close()

    finally:
        bs.logout()


if __name__ == "__main__":
    main()
