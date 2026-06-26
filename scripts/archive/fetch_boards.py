#!/usr/bin/env python3
"""Fetch all industry boards from eastmoney via direct API call."""
import urllib.request, json, re, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Try different API format
url = "https://push2.eastmoney.com/api/qt/clist/get"
params = "cb=jQuery1124&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f12,f14"
full_url = f"{url}?{params}"

req = urllib.request.Request(full_url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/',
})

try:
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        text = resp.read().decode('utf-8')
    print(f"OK: {len(text)} chars")
    m = re.search(r'\((\{.+})\)', text)
    if m:
        data = json.loads(m.group(1))
        items = data.get('data', {}).get('diff', [])
        print(f"Total: {len(items)}")
        for item in items:
            print(f"{item['f12']}\t{item['f14']}")
    else:
        print("No JSON match")
        print(text[:300])
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
