#!/usr/bin/env python3
"""Build stock→THS sector mapping using eastmoney MCP's client directly."""
import asyncio, json, sys
from mcp_eastmoney.eastmoney import EastmoneyClient

USER_SECTORS = ['能源金属', '半导体', '元件', '电子化学品', '化学纤维',
                '军工电子', '消费电子', '医疗服务', '光学光电子', '其他电子',
                '小金属', '贵金属', '机场航运', '工业金属']

async def main():
    c = EastmoneyClient()

    # Step 1: Get ALL industry boards (use the same API as sector_fund_flow but with larger limit)
    # The MCP tool only returns 50 max, but we can call the API directly
    url = "https://push2delay.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f12,f14"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as hc:
            r = await hc.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://data.eastmoney.com/',
            })
            data = r.json()
            items = data.get('data', {}).get('diff', [])

            # Build name->code map
            em_map = {}
            for item in items:
                name = item.get('f14', '')
                code = item.get('f12', '')
                if name and code:
                    em_map[name] = code

            print(f"Total EM industry boards: {len(em_map)}")

            # Match user sectors
            matched = {}
            for s in USER_SECTORS:
                if s in em_map:
                    matched[s] = ('industry', em_map[s])
                    print(f"  ✓ {s} → industry {em_map[s]}")
                else:
                    # Try fuzzy
                    for k, v in em_map.items():
                        if s in k or k in s:
                            matched[s] = ('industry', v, k)
                            print(f"  ~ {s} → {k} ({v})")
                            break
                    else:
                        print(f"  ✗ {s} → NOT FOUND in industry boards")
    except Exception as e:
        print(f"Error fetching industry boards: {e}")

    await c.aclose()

if __name__ == '__main__':
    asyncio.run(main())
