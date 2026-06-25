from __future__ import annotations

from datetime import date, datetime
from importlib import import_module
from inspect import Parameter, signature
from typing import Any

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    ProviderMetadata,
    StockDataSourceAdapter,
)


# =============================================================================
# 【小白必读】adata.py 是什么？
# =============================================================================
#
# AData 是另一个免费的 Python 金融数据库（https://github.com/1nchaos/adata）。
# 和 AKShare/BaoStock 类似，也是社区维护的数据源。
#
# AData 的 API 结构比较特殊 —— 它是层级式的：
#   client.stock.info.all_code()     → 股票列表
#   client.stock.market.get_market() → 日K线
#
# 注意这个点号链条：
#   client  →  .stock  →  .info  →  .all_code()
#                 ↓         ↓           ↓
#              stock模块   info子模块   具体函数
#
# 这和 AKShare 的扁平风格（client.stock_zh_a_hist()）不同。


# =============================================================================
# 工具函数
# =============================================================================


def _clean_text(value: Any) -> str | None:
    """清洗文本值。比 AKShare 版多处理了 "nan"、"NaN"、"None" 字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    # AData 可能返回字符串 "nan" / "NaN" / "None"（pandas 的 NaN 被转成字符串）
    if not text or text in {"-", "--", "nan", "NaN", "None"}:
        return None
    return text


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    """把 pandas DataFrame 转成字典列表。"""
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    if isinstance(frame, list):
        return [record for record in frame if isinstance(record, dict)]
    raise TypeError("AData returned an unsupported payload.")


def _supports_kwargs(func: Any) -> bool:
    """
    检查一个函数是否支持 **kwargs（任意关键字参数）。

    为什么需要这个？
      有些 AData 函数签名是 def get_market(stock_code, k_type, start_date):
      有些是 def get_market(stock_code, k_type, start_date, end_date):
      有些是 def get_market(**kwargs):

    如果函数支持 **kwargs，我们就可以放心传任意参数；
    如果不支持，就要小心只能用它能识别的参数。

    Parameter.VAR_KEYWORD 是 Python 里表示 **kwargs 的常量。
    """
    try:
        return any(
            parameter.kind == Parameter.VAR_KEYWORD
            for parameter in signature(func).parameters.values()
        )
    except (TypeError, ValueError):
        # 取不到签名时保守处理：假设支持（万一不支持会报 TypeError）
        return True


def _call_with_supported_kwargs(func: Any, **kwargs: Any) -> Any:
    """
    只传函数支持的参数，过滤掉不支持的。

    这是对 _supports_kwargs 的实际应用：
      ① 先检查函数是否接受 **kwargs → 是就直接全传
      ② 如果不是，读取签名 → 只传签名里有的参数

    示例：
      def foo(a, b): ...

      _call_with_supported_kwargs(foo, a=1, b=2, c=3)
      # c=3 不在 foo 的签名里，被过滤掉
      # 实际调用：foo(a=1, b=2)
    """
    try:
        func_signature = signature(func)
    except (TypeError, ValueError):
        # 取不到签名 → 全传（听天由命）
        return func(**kwargs)

    # 如果有 **kwargs → 全传（它能吃任何参数）
    if any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in func_signature.parameters.values()
    ):
        return func(**kwargs)

    # 过滤：只保留签名中存在的参数
    supported = {
        key: value
        for key, value in kwargs.items()
        if key in func_signature.parameters
    }
    return func(**supported)


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
    """
    把各种可能的交易所表示方式统一成 "SSE"/"SZSE"/"BSE"。

    AData 的数据来源多样，交易所字段可能出现各种写法：
      "SH"、"SSE"、"XSHG"、"上海" → 统一成 "SSE"
      "SZ"、"SZSE"、"XSHE"、"深圳" → 统一成 "SZSE"
      "BJ"、"BSE"、"北京"          → 统一成 "BSE"

    映射表里 XSHG / XSHE 是什么？
      这是交易所的 ISO 标准代码（用于国际市场）：
        XSHG = Shanghai Stock Exchange
        XSHE = Shenzhen Stock Exchange
    """
    text = (_clean_text(value) or "").upper()
    exchange_map = {
        "SH": "SSE",
        "SSE": "SSE",
        "XSHG": "SSE",     # ISO 标准代码
        "上海": "SSE",
        "SZ": "SZSE",
        "SZSE": "SZSE",
        "XSHE": "SZSE",    # ISO 标准代码
        "深圳": "SZSE",
        "BJ": "BSE",
        "BSE": "BSE",
        "北京": "BSE",
    }
    if text in exchange_map:
        return exchange_map[text]

    # 映射失败时靠代码前缀推断
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return "BSE"
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    return "SZSE"


def _split_symbol_and_exchange(
    raw_symbol: Any, raw_exchange: Any = None
) -> tuple[str | None, str | None]:
    """
    从各种可能的代码格式中提取 (纯代码, 交易所)。

    AData 的数据源不统一，代码可能有以下形式：
      ① "600519"                      → 纯代码
      ② "600519.SH"                   → 代码.后缀
      ③ "SH.600519"                   → 前缀.代码
      ④ "sh600519"                    → 前缀+代码（无分隔符）
      ⑤ "600519_SH"                   → 代码_后缀

    这个函数把所有这些情况统一成 (纯代码, 交易所)。

    为什么要这么复杂？
      AData 底层整合了多个数据源，每个数据源的代码格式不同。
      适配器的职责就是消化这些差异，输出统一格式。
    """
    text = _clean_text(raw_symbol)
    if text is None:
        return None, None

    # 把下划线统一成点号
    normalized = text.replace("_", ".")

    exchange_hint = raw_exchange

    # ---- 处理 "代码.后缀" 或 "前缀.代码" ----
    if "." in normalized:
        left, _, right = normalized.partition(".")
        if left.isdigit():
            # "600519.SH" → 代码=600519, 后缀=SH→合到exchange_hint
            normalized = left
            exchange_hint = exchange_hint or right
        elif right.isdigit():
            # "SH.600519" → 前缀=SH, 代码=600519
            normalized = right
            exchange_hint = exchange_hint or left
    else:
        # ---- 处理 "sh600519"（前缀+代码无分隔符） ----
        lower = normalized.lower()
        for prefix in ("sh", "sz", "bj"):
            if lower.startswith(prefix) and normalized[2:].isdigit():
                normalized = normalized[2:]  # 去掉前缀
                exchange_hint = exchange_hint or prefix
                break

    # 只保留数字字符
    symbol = "".join(
        character for character in normalized if character.isdigit()
    )
    if not symbol:
        return None, None

    return symbol, _normalize_exchange(exchange_hint, symbol=symbol)


def _status_from_record(record: dict[str, Any]) -> str:
    """
    从原始记录判断股票状态。

    支持多数据源的字段和值：
      status / list_status / 上市状态
      值："0" / "delisted" / "d" / "退市"          → DELISTED
      值："suspended" / "s" / "暂停"               → SUSPENDED
      其他                                             → LISTED

    同时检查股票名称里有没有"退"字（A 股退市股经常改名加"退"字）。
    """
    raw_status = (
        _clean_text(
            record.get("status")
            or record.get("list_status")
            or record.get("上市状态")
        )
        or ""
    ).lower()
    raw_name = (
        _clean_text(
            record.get("short_name")
            or record.get("name")
            or record.get("股票简称")
        )
        or ""
    ).lower()

    if raw_status in {"0", "delisted", "d", "退市"} or "退" in raw_name:
        return "DELISTED"
    if raw_status in {"suspended", "s", "暂停"}:
        return "SUSPENDED"
    return "LISTED"


# =============================================================================
# 主类：AData 适配器
# =============================================================================


class ADataAdapter(StockDataSourceAdapter):
    """
    AData 数据源适配器。

    特点：
      - 免费，社区维护
      - API 是层级式的：client.stock.info / client.stock.market
      - 数据格式不统一（整合了多个来源），需要更强的兼容处理
      - _split_symbol_and_exchange 是最复杂的工具函数，
        因为 AData 的代码格式最不统一
    """

    code = "adata"
    name = "AData"
    priority = 25         # 介于 BaoStock(20) 和 Tushare(30) 之间
    requires_token = False
    default_enabled = True

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
            provider_type="python_package",
            homepage_url="https://github.com/1nchaos/adata",
            docs_url="https://adata.30006124.xyz/",
            auth_mode="none",
            stability="community",
            rate_limit_note="Uses AData public A-share data APIs; upstream public endpoints may rate-limit.",
            install_note="Install optional package: pip install adata.",
        )

    def health_check(self) -> HealthCheckResult:
        """
        检查 AData 是否可用。

        AData 的 API 是层级式的，所以用 getattr 逐层访问：
          client.stock.info.all_code      → 股票列表
          client.stock.market.get_market  → 日K线

        用 getattr(obj, "attr", None) 来安全访问，
        避免中间某一层不存在时直接 AttributeError。
        """
        try:
            client = self._get_client()

            # getattr 逐层下沉：client → .stock → .info → 检查 .all_code
            stock = getattr(client, "stock", None)
            info = getattr(stock, "info", None)
            market = getattr(stock, "market", None)

            if not hasattr(info, "all_code") or not hasattr(
                market, "get_market"
            ):
                return HealthCheckResult(
                    healthy=False,
                    status="unhealthy",
                    message="AData is installed, but stock.info.all_code or stock.market.get_market was not found.",
                )
        except ModuleNotFoundError:
            return HealthCheckResult(
                healthy=False,
                status="unavailable",
                message="AData is not installed. Install the optional adata package to enable this source.",
            )
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, status="unhealthy", message=str(exc)
            )

        return HealthCheckResult(
            healthy=True,
            status="healthy",
            message="AData package is available.",
        )

    # ===== 获取股票列表 =====

    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        从 AData 获取 A 股股票列表。

        AData 的调用链：client.stock.info.all_code()
        注意：这是层级式的，不是 AKShare 的扁平调用。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "AData stock list adapter currently supports A_SHARE only."
            )

        client = self._get_client()
        info = getattr(getattr(client, "stock", None), "info", None)
        if not hasattr(info, "all_code"):
            raise RuntimeError(
                "AData client does not expose stock.info.all_code."
            )
        return _records_from_frame(info.all_code())

    def normalize_stock_list(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedStock]:
        """
        把 AData 原始股票列表转成统一格式。

        由于 AData 数据来源不统一，字段名也必须做多源兼容：
          stock_code / code / 股票代码 / 证券代码
          short_name / stock_name / name / 股票简称 / 名称
        """
        normalized: list[NormalizedStock] = []

        for record in raw_records:
            symbol, exchange = _split_symbol_and_exchange(
                record.get("stock_code")
                or record.get("code")
                or record.get("股票代码")
                or record.get("证券代码"),
                record.get("exchange") or record.get("交易所"),
            )
            name = _clean_text(
                record.get("short_name")
                or record.get("stock_name")
                or record.get("name")
                or record.get("股票简称")
                or record.get("名称")
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
                    # ★ AData 支持退市/暂停状态，AKShare 统一写 "LISTED"
                    industry=_clean_text(
                        record.get("industry") or record.get("行业")
                    ),
                    listing_date=_parse_date(
                        record.get("list_date")
                        or record.get("listing_date")
                        or record.get("上市日期")
                    ),
                    delisting_date=_parse_date(
                        record.get("delist_date")
                        or record.get("delisting_date")
                        or record.get("退市日期")
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
    ) -> list[dict[str, Any]]:
        """
        从 AData 获取日K线数据。

        AData 的调用链：client.stock.market.get_market(...)

        特殊处理：
          AData 某些版本的 get_market 不支持 end_date 参数。
          代码里先尝试传 end_date，如果 TypeError 就去掉 end_date 再试。
          这是兼容不同 AData 版本的妥协方案。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "AData daily bars adapter currently supports A_SHARE only."
            )

        client = self._get_client()
        market_api = getattr(
            getattr(client, "stock", None), "market", None
        )
        if not hasattr(market_api, "get_market"):
            raise RuntimeError(
                "AData client does not expose stock.market.get_market."
            )

        get_market = market_api.get_market
        kwargs: dict[str, Any] = {
            "stock_code": symbol,
            "k_type": 1,  # 1 = 日线
            "start_date": start_date.isoformat(),
        }

        try:
            # 优先传 end_date
            frame = _call_with_supported_kwargs(get_market, **kwargs)
        except TypeError:
            # 如果函数不支持 end_date，就去掉它重试
            if _supports_kwargs(get_market) or "end_date" not in kwargs:
                raise
            frame = _call_with_supported_kwargs(
                get_market,
                **{
                    key: value
                    for key, value in kwargs.items()
                    if key != "end_date"
                },
            )

        return _records_from_frame(frame)

    def normalize_daily_bars(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedDailyBar]:
        """
        把 AData 原始日K线转成统一格式。

        和 normalize_stock_list 一样，字段名要兼容多源：
          stock_code / code / symbol / 股票代码
          trade_date / trade_time / date / 日期
        """
        normalized: list[NormalizedDailyBar] = []

        for record in raw_records:
            symbol, exchange = _split_symbol_and_exchange(
                record.get("stock_code")
                or record.get("code")
                or record.get("symbol")
                or record.get("股票代码"),
                record.get("exchange") or record.get("交易所"),
            )
            trade_date = _parse_date(
                record.get("trade_date")
                or record.get("trade_time")
                or record.get("date")
                or record.get("日期")
            )

            if symbol is None or exchange is None or trade_date is None:
                continue

            open_price = _to_float(
                record.get("open") or record.get("开盘")
            )
            high = _to_float(record.get("high") or record.get("最高"))
            low = _to_float(record.get("low") or record.get("最低"))
            close = _to_float(record.get("close") or record.get("收盘"))

            if (
                open_price is None
                or high is None
                or low is None
                or close is None
            ):
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
                    pre_close=_to_float(
                        record.get("pre_close")
                        or record.get("preclose")
                        or record.get("前收盘")
                    ),
                    volume=_to_float(
                        record.get("volume")
                        or record.get("vol")
                        or record.get("成交量"),
                        default=0.0,
                    )
                    or 0.0,
                    amount=_to_float(
                        record.get("amount") or record.get("成交额"),
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
        """懒加载 AData 模块。"""
        if self._client is None:
            self._client = import_module("adata")
        return self._client
