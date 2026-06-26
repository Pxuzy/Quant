#!/usr/bin/env python3
"""Search for missing sectors (贵金属, 军工电子, 其他电子, 机场航运)."""
import asyncio, httpx

HOST = "https://push2delay.eastmoney.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}

async def get_boards(fs_filter: str) -> dict:
    url = f"{HOST}/api/qt/clist/get?cb=&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs={fs_filter}&fields=f12,f14"
    async with httpx.AsyncClient(timeout=15.0) as hc:
        r = await hc.get(url, headers=HEADERS)
        data = r.json()
        return {item['f14']: item['f12'] for item in data.get('data', {}).get('diff', [])}

async def main():
    ind = await get_boards("m:90+t:2")
    con = await get_boards("m:90+t:3")

    # Search for 贵 metal
    targets = ['贵金属', '黄金', '白银', '军工', '军工电子', '航空机场', '机场']
    for t in targets:
        print(f"\nSearching '{t}':")
        for name, code in sorted(ind.items()):
            if t in name:
                print(f"  IND: {code} {name}")
        for name, code in sorted(con.items()):
            if t in name:
                print(f"  CON: {code} {name}")

if __name__ == '__main__':
    asyncio.run(main())
