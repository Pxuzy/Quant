#!/usr/bin/env python3
"""Get EM board names with proxy."""
import os
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

import akshare as ak

names_em = ak.stock_board_industry_name_em()
print(f"Total: {len(names_em)}")

# Map user sectors to EM codes
USER_SECTORS = ['能源金属', '半导体', '元件', '电子化学品', '化学纤维',
                '军工电子', '消费电子', '医疗服务', '光学光电子', '其他电子',
                '小金属', '贵金属', '机场航运', '工业金属']

em_name_to_code = {}
for _, row in names_em.iterrows():
    name = str(row.get('板块名称', '')).strip()
    code = str(row.get('代码', '')).strip()
    if name and code:
        em_name_to_code[name] = code

print("\n--- Matching user sectors to EM boards ---")
for s in USER_SECTORS:
    if s in em_name_to_code:
        print(f"  ✓ {s} → {em_name_to_code[s]}")
    else:
        # Fuzzy search
        for k, v in em_name_to_code.items():
            if s in k or k in s:
                print(f"  ~ {s} → {k} ({v})")
                break
        else:
            print(f"  ✗ {s} → NOT FOUND")
