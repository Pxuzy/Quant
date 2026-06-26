#!/usr/bin/env python3
"""Rebuild sector map with corrected mappings."""
import asyncio, json, httpx
from datetime import datetime

# CORRECTED BK mappings after search:
CORRECTED_MAP = {
    '能源金属': 'BK1015',     # industry ✓
    '半导体': 'BK1036',      # industry ✓
    '元件': 'BK0459',        # industry ✓
    '电子化学品': 'BK1332',   # industry (电子化学品Ⅲ) ✓
    '化学纤维': 'BK0471',    # industry ✓
    '军工电子': 'BK1233',    # industry (军工电子Ⅱ) ✓
    '消费电子': 'BK1037',    # industry ✓
    '医疗服务': 'BK0727',    # industry ✓
    '光学光电子': 'BK1038',  # industry ✓
    '其他电子': None,        # TBD
    '小金属': 'BK1027',     # industry ✓
    '贵金属': 'BK1617',     # industry (黄金) - closest match
    '机场航运': 'BK0420',   # industry (航空机场) ✓
    '工业金属': 'BK1287',   # industry ✓
}

HOST = "https://push2delay.eastmoney.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}

async def get_board_constituents(bk_code: str) -> list:
    url = f"{HOST}/api/qt/clist/get?cb=&pn=1&pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=b:{bk_code}+f:!50&fields=f12,f14"
    async with httpx.AsyncClient(timeout=15.0) as hc:
        try:
            r = await hc.get(url, headers=HEADERS)
            data = r.json()
            return [item['f12'] for item in data.get('data',{}).get('diff',[]) if item.get('f12')]
        except:
            return []

async def main():
    valid = {s: bk for s, bk in CORRECTED_MAP.items() if bk}
    stock_to_sectors = {}
    sector_to_stocks = {}

    # Also search for 其他电子 in all boards
    async with httpx.AsyncClient(timeout=15.0) as hc:
        r1 = await hc.get(f"{HOST}/api/qt/clist/get?cb=&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f12,f14", headers=HEADERS)
        r2 = await hc.get(f"{HOST}/api/qt/clist/get?cb=&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:3&fields=f12,f14", headers=HEADERS)
        all_boards = {}
        for data in [r1.json(), r2.json()]:
            for item in data.get('data',{}).get('diff',[]):
                all_boards[item['f14']] = item['f12']

    # Try to find 其他电子
    for name, code in sorted(all_boards.items()):
        if '其他电子' in name:
            print(f"Found ~其他电子: {code} {name}")
            valid['其他电子'] = code
            break
    else:
        print("其他电子: NOT FOUND in any board")

    print(f"\nFetching constituents...")
    for sector_name, bk_code in sorted(valid.items()):
        print(f"  {sector_name} ({bk_code})...", end=' ', flush=True)
        stocks = await get_board_constituents(bk_code)
        if stocks:
            for sym in stocks:
                stock_to_sectors.setdefault(sym, []).append(sector_name)
            sector_to_stocks[sector_name] = stocks
            print(f"{len(stocks)} stocks")
        else:
            print("0 stocks")
        await asyncio.sleep(0.2)

    result = {
        'updated_at': datetime.now().isoformat(),
        'sectors': list(valid.keys()),
        'sector_bk_codes': valid,
        'sector_to_stocks': {s: sorted(codes) for s, codes in sector_to_stocks.items()},
        'stock_to_sectors': stock_to_sectors,
        'total_sectors': len(valid),
        'total_stocks': len(stock_to_sectors),
    }

    path = r'E:\hermes\workspace\Quant\data\mcp_cache\ths_sector_map.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved: {len(stock_to_sectors)} stocks, {len(valid)} sectors")
    for s in sorted(sector_to_stocks.keys()):
        print(f"  {s}: {len(sector_to_stocks[s])} stocks")

if __name__ == '__main__':
    asyncio.run(main())
