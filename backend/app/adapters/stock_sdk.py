from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from backend.app.adapters._http import (
    _NodeStockSdkClient,
)
from backend.app.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    ProviderMetadata,
    StockDataSourceAdapter,
    normalize_daily_bar_adjust_type,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 【小白必读】stock_sdk.py 是什么？
# =============================================================================
#
# 这个适配器和其他所有适配器都不同 —— 它不是调用 Python 包，
# 而是启动一个 Node.js 子进程来运行 stock-sdk（一个 JavaScript/TypeScript 包）。
#
# 为什么会有这种设计？
#   某些股票数据 SDK 只有 Node.js 版本，没有 Python 版本。
#   与其等别人写 Python 封装，不如直接用子进程调用 Node.js 脚本。
#
# 工作原理：
#   Python（主进程）
#     │
#     ├─ subprocess.run(["node", "-e", NODE_STOCK_SDK_SCRIPT], input=json)
#     │
#     └─ Node.js 子进程
#          ├─ require("stock-sdk")
#          ├─ 调用对应的函数
#          └─ stdout 输出 JSON 结果
#
# 这是一种常见的"跨语言调用"模式：
#   Python ←—JSON→ Node.js（通过标准输入/输出通信）
#
# 这个文件的特殊之处：
#   ① 内含一大段 JavaScript 代码（NODE_STOCK_SDK_SCRIPT）
#   ② 用 subprocess 启动 Node.js 进程
#   ③ 通过 JSON 标准输入/输出和子进程通信
#   ④ 需要 Node.js 环境 + stock-sdk npm 包
#
# 重构说明：
#   HTTP / 子进程传输层（NODE_STOCK_SDK_SCRIPT、_NodeStockSdkNamespace、
#   _NodeStockSdkClient、_stock_sdk_cwd）已抽取到 ``_http.py``。
#   这里仅保留适配器类 + 数据归一化逻辑，并通过 ``from … import`` 重新
#   导出，保证 ``from backend.app.adapters.stock_sdk import …`` 公共接口不变。


# =============================================================================
# Python 端工具函数（数据归一化层）
# =============================================================================


def _clean_text(value: Any) -> str | None:
    """清洗文本值。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "nan", "NaN", "None"}:
        return None
    return text


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    """
    从 Node.js 返回的 JSON 中提取字典列表。

    这个函数比 _records_from_frame 更复杂，因为：
      Node.js 返回的 JSON 格式不固定 ——
      有时直接是数组 [{...}, {...}]
      有时是 {"data": [{...}], "total": 100}
      有时是 {"items": [{...}]}
      有时数组元素是字符串而不是字典

    这个函数把所有这些情况都兜住，输出统一的字典列表。
    """

    def record_from_item(item: Any) -> dict[str, Any] | None:
        """把单个元素转成字典。"""
        if isinstance(item, dict):
            return item
        # 如果元素是字符串，创建一个 {"code": 字符串, "name": 字符串} 的字典
        text = _clean_text(item)
        if text is None:
            return None
        return {"code": text, "name": text}

    # 情况一：pandas DataFrame（极少数情况，Node.js 端可能返回）
    if hasattr(payload, "to_dict"):
        records = payload.to_dict(orient="records")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]

    # 情况二：直接就是数组（最常见）
    if isinstance(payload, list):
        return [record for item in payload if (record := record_from_item(item)) is not None]

    # 情况三：带包装的对象 {"data": [...], "total": 100}
    if isinstance(payload, dict):
        for key in ("data", "items", "records", "list", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [record for item in value if (record := record_from_item(item)) is not None]
        # 如果就是一个普通的单条记录，直接包成列表
        return [payload]

    raise TypeError("stock-sdk returned an unsupported payload.")


def _parse_date(value: Any) -> date | None:
    """解析各种可能的日期格式。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean_text(value)
    if text is None:
        return None
    digits = text.replace("-", "").replace("/", "")[:8]
    if len(digits) == 8 and digits.isdigit():
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    return date.fromisoformat(text.replace("/", "-")[:10])


def _to_float(value: Any, *, default: float | None = None) -> float | None:
    """安全转浮点数。"""
    text = _clean_text(value)
    if text is None:
        return default
    return float(text)


def _normalize_exchange(value: Any, *, symbol: str) -> str:
    """统一交易所代码（和 adata.py 里逻辑一致）。"""
    text = (_clean_text(value) or "").upper()
    exchange_map = {
        "SH": "SSE",
        "SSE": "SSE",
        "XSHG": "SSE",
        "上海": "SSE",
        "SZ": "SZSE",
        "SZSE": "SZSE",
        "XSHE": "SZSE",
        "深圳": "SZSE",
        "BJ": "BSE",
        "BSE": "BSE",
        "北京": "BSE",
    }
    if text in exchange_map:
        return exchange_map[text]
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return "BSE"
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    return "SZSE"


def _split_symbol_and_exchange(raw_symbol: Any, raw_exchange: Any = None) -> tuple[str | None, str | None]:
    """从各种代码格式中提取 (纯代码, 交易所)，和 adata.py 逻辑一致。"""
    text = _clean_text(raw_symbol)
    if text is None:
        return None, None

    normalized = text.replace("_", ".")
    exchange_hint = raw_exchange

    if "." in normalized:
        left, _, right = normalized.partition(".")
        if left.isdigit():
            normalized = left
            exchange_hint = exchange_hint or right
        elif right.isdigit():
            normalized = right
            exchange_hint = exchange_hint or left
    else:
        lower = normalized.lower()
        for prefix in ("sh", "sz", "bj"):
            if lower.startswith(prefix) and normalized[2:].isdigit():
                normalized = normalized[2:]
                exchange_hint = exchange_hint or prefix
                break

    symbol = "".join(character for character in normalized if character.isdigit())
    if not symbol:
        return None, None
    return symbol, _normalize_exchange(exchange_hint, symbol=symbol)


def _status_from_record(record: dict[str, Any]) -> str:
    """判断股票状态，和 adata.py 逻辑一致。"""
    raw_status = (
        _clean_text(record.get("status") or record.get("listStatus") or record.get("list_status")) or ""
    ).lower()
    raw_name = (_clean_text(record.get("name") or record.get("shortName") or record.get("short_name")) or "").lower()

    if raw_status in {"0", "delisted", "d", "退市"} or "退" in raw_name:
        return "DELISTED"
    if raw_status in {"suspended", "s", "暂停"}:
        return "SUSPENDED"
    return "LISTED"


# =============================================================================
# 主类：Stock SDK 适配器
# =============================================================================


class StockSdkAdapter(StockDataSourceAdapter):
    """
    Stock SDK 适配器 —— 通过 Node.js 子进程调用 stock-sdk。

    和其他适配器的关键区别：
      - 不是 import Python 包，而是 subprocess.run Node.js
      - provider_type = "node_package"（而非 "python_package"）
      - 默认不启用（因为需要 Node.js + npm 环境）
      - 优先级最低（45），作为最后的备选方案
    """

    code = "stock_sdk"
    name = "Stock SDK"
    priority = 45  # ★ 最低优先级，实验性质
    requires_token = False
    default_enabled = False  # ★ 默认关闭，需要用户手动配置 Node 环境

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            stock_list=True,
            daily_bars=True,
            daily_bar_exchanges=("SSE", "SZSE", "BSE"),
        )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_type="node_package",  # ★ 注意：不是 python_package
            homepage_url="https://github.com/chengzuopeng/stock-sdk",
            docs_url="https://stock-sdk-v2.linkdiary.cn/",
            auth_mode="none",
            stability="community",
            rate_limit_note="Uses stock-sdk public upstream data sources; keep this source disabled unless the Node package is installed.",
            install_note="Install optional Node package in frontend or STOCK_SDK_CWD: npm install stock-sdk@beta.",
        )

    def health_check(self) -> HealthCheckResult:
        """
        检查 Node.js + stock-sdk 是否可用。

        和 Python 适配器不同，这里的 health_check 会真的启动 Node 子进程。
        所以如果 Node 没装，这里就会暴露出来。
        """
        try:
            client = self._get_client()
            if hasattr(client, "health_check"):
                result = client.health_check()
                if not result.get("hasCodes") or not result.get("hasKline"):
                    return HealthCheckResult(
                        healthy=False,
                        status="unhealthy",
                        message="stock-sdk is installed, but stock list or kline APIs were not found.",
                    )
            else:
                codes = getattr(client, "codes", None)
                kline = getattr(client, "kline", None)
                if not hasattr(codes, "cn") or not hasattr(kline, "cn"):
                    return HealthCheckResult(
                        healthy=False,
                        status="unhealthy",
                        message="stock-sdk client does not expose codes.cn and kline.cn.",
                    )
        except ModuleNotFoundError as exc:
            logger.warning("stock-sdk health check failed (unavailable): %s", exc)
            return HealthCheckResult(healthy=False, status="unavailable", message=str(exc))
        except Exception as exc:
            logger.warning("stock-sdk health check failed: %s", exc)
            return HealthCheckResult(healthy=False, status="unhealthy", message=str(exc))

        return HealthCheckResult(
            healthy=True,
            status="healthy",
            message="stock-sdk package is available.",
        )

    # ===== 获取股票列表 =====

    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        通过 Node.js 子进程获取股票列表。

        调用链：
          Python fetch_stock_list()
            → client.codes.cn(market="A_SHARE")
              → _NodeStockSdkNamespace.cn()
                → _NodeStockSdkClient.run("codes.cn", {...})
                  → subprocess.run(node -e SCRIPT)
                    → Node.js: callStockList({market: "A_SHARE"})
                      → sdk.codes.cn({market: "A_SHARE"})
                        → stdout: JSON 数组
        """
        if market.upper() != "A_SHARE":
            raise ValueError("stock-sdk stock list adapter currently supports A_SHARE only.")

        client = self._get_client()
        codes = getattr(client, "codes", None)
        if not hasattr(codes, "cn"):
            raise RuntimeError("stock-sdk client does not expose codes.cn.")
        return _records_from_payload(codes.cn(market="A_SHARE"))

    def normalize_stock_list(self, raw_records: list[dict[str, Any]]) -> list[NormalizedStock]:
        """
        把 stock-sdk 原始数据转成统一格式。

        stock-sdk 的字段名是 camelCase 风格（JavaScript 惯例）：
          code / symbol / stockCode / stock_code
          name / shortName / short_name / stockName
          listDate / list_date / listingDate
        """
        normalized: list[NormalizedStock] = []

        for record in raw_records:
            symbol, exchange = _split_symbol_and_exchange(
                record.get("code") or record.get("symbol") or record.get("stockCode") or record.get("stock_code"),
                record.get("exchange") or record.get("market"),
            )
            name = _clean_text(
                record.get("name") or record.get("shortName") or record.get("short_name") or record.get("stockName")
            )

            if symbol is None or exchange is None or name is None:
                continue

            normalized.append(
                NormalizedStock(
                    symbol=symbol,
                    exchange=exchange,
                    market="A_SHARE",
                    name=name,
                    status=_status_from_record(record),
                    industry=_clean_text(record.get("industry") or record.get("sector")),
                    listing_date=_parse_date(
                        record.get("listDate") or record.get("list_date") or record.get("listingDate")
                    ),
                    delisting_date=_parse_date(
                        record.get("delistDate") or record.get("delist_date") or record.get("delistingDate")
                    ),
                    source=self.code,
                )
            )

        return normalized

    # ===== 获取日K线 =====

    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        market: str,
        start_date: date,
        end_date: date,
        adjust_type: str = "none",
    ) -> list[dict[str, Any]]:
        """
        通过 Node.js 子进程获取日K线。

        和 fetch_stock_list 一样通过 client.kline.cn() → subprocess → Node.js 的链路。
        同时传 snake_case 和 camelCase 的参数，兼容 stock-sdk 的不同版本。
        """
        if market.upper() != "A_SHARE":
            raise ValueError("stock-sdk daily bars adapter currently supports A_SHARE only.")
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        if adjust_type_code != "none":
            raise ValueError("stock-sdk daily bars adapter currently supports unadjusted bars only.")

        client = self._get_client()
        kline = getattr(client, "kline", None)
        if not hasattr(kline, "cn"):
            raise RuntimeError("stock-sdk client does not expose kline.cn.")
        return _records_from_payload(
            kline.cn(
                symbol=symbol,
                code=symbol,
                exchange=exchange,
                period="daily",
                adjust="",
                # 同时传两种命名风格，兼容不同版本
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                startDate=start_date.strftime("%Y%m%d"),
                endDate=end_date.strftime("%Y%m%d"),
            )
        )

    def normalize_daily_bars(self, raw_records: list[dict[str, Any]]) -> list[NormalizedDailyBar]:
        """
        把 stock-sdk 原始日K线转成统一格式。

        字段名兼容 snake_case 和 camelCase：
          code / symbol / stockCode / stock_code
          date / tradeDate / trade_date / day
          open / openPrice, close / closePrice, ...
        """
        normalized: list[NormalizedDailyBar] = []

        for record in raw_records:
            symbol, exchange = _split_symbol_and_exchange(
                record.get("code") or record.get("symbol") or record.get("stockCode") or record.get("stock_code"),
                record.get("exchange") or record.get("market"),
            )
            trade_date = _parse_date(
                record.get("date") or record.get("tradeDate") or record.get("trade_date") or record.get("day")
            )

            if symbol is None or exchange is None or trade_date is None:
                continue

            open_price = _to_float(record.get("open") or record.get("openPrice"))
            high = _to_float(record.get("high") or record.get("highPrice"))
            low = _to_float(record.get("low") or record.get("lowPrice"))
            close = _to_float(record.get("close") or record.get("closePrice"))

            if open_price is None or high is None or low is None or close is None:
                continue

            normalized.append(
                NormalizedDailyBar(
                    symbol=symbol,
                    exchange=exchange,
                    market="A_SHARE",
                    trade_date=trade_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    pre_close=_to_float(record.get("preClose") or record.get("pre_close") or record.get("preclose")),
                    volume=_to_float(
                        record.get("volume") or record.get("vol"),
                        default=0.0,
                    )
                    or 0.0,
                    amount=_to_float(
                        record.get("amount") or record.get("turnover"),
                        default=0.0,
                    )
                    or 0.0,
                    adjust_factor=1.0,
                    adjust_type="none",
                    source=self.code,
                )
            )

        return normalized

    def _get_client(self) -> Any:
        """
        获取 Stock SDK 客户端。

        和其他适配器的 _get_client 不同：
          这里不是 import Python 模块，
          而是创建一个管理 Node.js 子进程的 Python 对象。
        """
        if self._client is None:
            self._client = _NodeStockSdkClient()
        return self._client
