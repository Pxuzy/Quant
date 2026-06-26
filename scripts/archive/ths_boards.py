#!/usr/bin/env python3
"""Scrape THS industry board data for Quant project."""
import json, sys, re

akshare_ok = False
try:
    import akshare as ak
    import pandas as pd
    _ = ak.stock_board_industry_name_ths
    akshare_ok = True
except Exception:
    pass

USER_SECTORS = ['能源金属', '半导体', '元件', '电子化学品', '化学纤维',
                '军工电子', '消费电子', '医疗服务', '光学光电子', '其他电子',
                '小金属', '贵金属', '机场航运', '工业金属']

if not akshare_ok:
    print("ERROR: akshare not available")
    sys.exit(1)

# Step 1: Get all THS board names
names = ak.stock_board_industry_name_ths()
# Step 2: Build mapping
name_to_code = {}
for _, row in names.iterrows():
    name = str(row.get('name', '')).strip()
    code = str(row.get('code', '')).strip()
    if name and code:
        name_to_code[name] = code

# Step 3: Find user's sectors
found = {}
for s in USER_SECTORS:
    if s in name_to_code:
        found[s] = name_to_code[s]
    else:
        # Try fuzzy match
        for k, v in name_to_code.items():
            if s in k or k in s:
                found[s] = (k, v)
                break

for s in USER_SECTORS:
    if s in found:
        v = found[s]
        if isinstance(v, tuple):
            print(f"  ~ {s} → {v[0]} ({v[1]})")
        else:
            print(f"  ✓ {s} → {v}")
    else:
        print(f"  ✗ {s} → NOT FOUND")

# Step 4: Get constituents for each found sector
print("\n--- All THS boards (first 50) ---")
for i, (name, code) in enumerate(sorted(name_to_code.items())):
    if i < 50:
        print(f"  {code}: {name}")
