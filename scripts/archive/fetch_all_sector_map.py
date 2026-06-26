#!/usr/bin/env python3
"""Full THS sector→EM board mapping - searches industry + concept boards."""
import asyncio, json, httpx
from datetime import datetime

USER_SECTORS = ['能源金属', '半导体', '元件', '电子化学品', '化学纤维',
                '军工电子', '消费电子', '医疗服务', '光学光电子', '其他电子',
                '小金属', '贵金属', '机场航运', '工业金属']

HOST = "https://push2delay.eastmoney.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}

async def get_boards(fs_filter: str) -> dict:
    """Get boards by filter. fs=m:90+t:2 for industry, m:90+t:3 for concept."""
    url = f"{HOST}/api/qt/clist/get?cb=&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs={fs_filter}&fields=f12,f14"
    async with httpx.AsyncClient(timeout=15.0) as hc:
        r = await hc.get(url, headers=HEADERS)
        data = r.json()
        return {item['f14']: item['f12'] for item in data.get('data', {}).get('diff', [])}

async def get_board_constituents(bk_code: str) -> list:
    """Get constituent stock codes for a board."""
    url = f"{HOST}/api/qt/clist/get?cb=&pn=1&pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=b:{bk_code}+f:!50&fields=f12,f14"
    async with httpx.AsyncClient(timeout=15.0) as hc:
        try:
            r = await hc.get(url, headers=HEADERS)
            data = r.json()
            return [item['f12']for item in data.get('data',{}).get('diff',[]) if item.get('f12')]
        except Exception as e:
            return []

def find_best_match(name: str, boards: dict) -> str | None:
    """Find best matching BK code for a sector name."""
    if name in boards:
        return boards[name]  # exact match
    # Fuzzy match
    for k, v in boards.items():
        if name in k or k in name:
            return v
    return None

async def main():
    print("Fetching industry boards...")
    ind = await get_boards("m:90+t:2")
    print(f"  {len(ind)} industry boards")

    print("Fetching concept boards...")
    con = await get_boards("m:90+t:3")
    print(f"  {len(con)} concept boards")

    combined = {'industry': ind, 'concept': con}

    # For each user sector, try industry first, then concept
    final_map = {}
    for s in USER_SECTORS:
        # Try industry exact
        if s in ind:
            final_map[s] = ('industry', ind[s])
            continue
        # Try concept exact
        if s in con:
            # Check if concept name is a better match than an industry partial
            final_map[s] = ('concept', con[s])
            continue
        # Fuzzy industry
        for k, v in ind.items():
            if s in k or k in s:
                final_map[s] = ('industry', v, k)
                break
        else:
            # Fuzzy concept
            for k, v in con.items():
                if s in k or k in s:
                    final_map[s] = ('concept', v, k)
                    break
            else:
                final_map[s] = ('NOT_FOUND', None)

    print("\n=== Sector→BK Mapping ===")
    for s in USER_SECTORS:
        v = final_map[s]
        if v[0] == 'NOT_FOUND':
            print(f"  ✗ {s}: NOT FOUND")
        elif len(v) == 3:
            print(f"  ~ {s}: {v[0]} {v[2]} ({v[1]})")
        else:
            print(f"  ✓ {s}: {v[0]} {v[1]}")

    # Fetch constituents
    print("\n=== Fetching constituents ===")
    stock_to_sectors = {}
    sector_to_stocks = {}

    for s in USER_SECTORS:
        v = final_map[s]
        if v[0] == 'NOT_FOUND' or v[1] is None:
            continue
        bk = v[1]
        print(f"  {s} ({bk})...", end=' ', flush=True)
        stocks = await get_board_constituents(bk)
        if stocks:
            for sym in stocks:
                stock_to_sectors.setdefault(sym, []).append(s)
            sector_to_stocks[s] = stocks
            print(f"{len(stocks)} stocks")
        else:
            print("0 stocks")
        await asyncio.sleep(0.2)

    # Save
    result = {
        'updated_at': datetime.now().isoformat(),
        'sectors': USER_SECTORS,
        'sector_mapping': {s: v for s, v in final_map.items()},
        'sector_to_stocks': {s: sorted(codes) for s, codes in sector_to_stocks.items()},
        'stock_to_sectors': stock_to_sectors,
        'total_sectors': len([s for s in USER_SECTORS if final_map[s][0] != 'NOT_FOUND']),
        'total_stocks': len(stock_to_sectors),
    }

    path = r'E:\hermes\workspace\Quant\data\mcp_cache\ths_sector_map.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved to {path}")
    print(f"  {len(stock_to_sectors)} stocks across {len(sector_to_stocks)} sectors")
    for s in sorted(sector_to_stocks.keys()):
        print(f"  {s}: {len(sector_to_stocks[s])} stocks")

if __name__ == '__main__':
    asyncio.run(main())
