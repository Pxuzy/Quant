"""共享 HTTP 请求工具。"""

from __future__ import annotations

import urllib.request
from time import time

_request_cache: dict[str, tuple[float, str]] = {}


def _request(url: str, headers: dict = None, timeout: int = 10, encoding: str = "utf-8") -> str:
    now = time()
    cached = _request_cache.get(url)
    if cached and (now - cached[0]) < 2.0:
        return cached[1]
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = resp.read().decode(encoding, errors="ignore")
    _request_cache[url] = (now, result)
    return result
