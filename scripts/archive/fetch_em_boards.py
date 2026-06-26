#!/usr/bin/env python3
"""Get eastmoney industry board names and map THS sectors to EM codes."""
import akshare as ak
import pandas as pd

# Get all eastmoney industry boards
names_em = ak.stock_board_industry_name_em()
print(f"EM boards: {len(names_em)}")
# Show columns and names
print("Columns:", list(names_em.columns))
for _, row in names_em.iterrows():
    print(f"  {row.get('代码','')}\t{row.get('板块名称','')}")

print("\n\n" + "="*60)

# Try to find constituents for our THS sectors
# Eastmoney names use different naming than THS
# Our sectors: 能源金属, 半导体, 元件, 电子化学品, 化学纤维, 军工电子,
#              消费电子, 医疗服务, 光学光电子, 其他电子,
#              小金属, 贵金属, 机场航运, 工业金属
