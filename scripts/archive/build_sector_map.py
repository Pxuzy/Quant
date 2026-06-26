#!/usr/bin/env python3
"""Build stock→THS sector mapping from akshare."""
import json, sys, time
import akshare as ak
import pandas as pd

USER_SECTORS = {
    '能源金属': '881267', '半导体': '881121', '元件': '881270',
    '电子化学品': '881172', '化学纤维': '881264', '军工电子': '881276',
    '消费电子': '881124', '医疗服务': '881175', '光学光电子': '881122',
    '其他电子': '881123', '小金属': '881170', '贵金属': '881169',
    '机场航运': '881151', '工业金属': '881168',
}

# Build stock→sector mapping
stock_to_sectors = {}  # symbol -> [sector_names]
sector_to_stocks = {}  # sector_name -> [symbols]

for sector_name, sector_code in USER_SECTORS.items():
    print(f"Fetching {sector_name} ({sector_code})...", end=' ', flush=True)
    try:
        df = ak.stock_board_industry_cons_ths(symbol=sector_name)
        stocks = []
        for _, row in df.iterrows():
            symbol = str(row.get('代码', '')).strip()
            name = str(row.get('名称', '')).strip()
            if symbol and len(symbol) == 6:
                stocks.append(symbol)
                stock_to_sectors.setdefault(symbol, []).append(sector_name)
        sector_to_stocks[sector_name] = stocks
        print(f"{len(stocks)} stocks")
    except Exception as e:
        print(f"FAIL: {e}")
    time.sleep(0.5)  # Rate limit

# Save
result = {
    'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'sectors': list(USER_SECTORS.keys()),
    'sector_to_stocks': {s: sorted(codes) for s, codes in sector_to_stocks.items()},
    'stock_to_sectors': stock_to_sectors,
    'total_sectors': len(USER_SECTORS),
    'total_stocks': len(stock_to_sectors),
}

with open(r'E:\hermes\workspace\Quant\data\mcp_cache\ths_sector_map.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\nDone! {len(stock_to_sectors)} stocks mapped across {len(USER_SECTORS)} sectors")
# Show summary
for s, codes in sorted(sector_to_stocks.items()):
    print(f"  {s}: {len(codes)} stocks")
