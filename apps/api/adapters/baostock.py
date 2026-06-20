from __future__ import annotations

from datetime import date
from importlib import import_module
from time import sleep
from typing import Any

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    NormalizedTradingCalendar,
    ProviderMetadata,
    StockDataSourceAdapter,
)


# =============================================================================
# 【小白必读】baostock.py 是什么？
# =============================================================================
#
# BaoStock（证券宝）是一个免费的 Python 金融数据库。
# 和 AKShare 一样，它提供 A 股数据，但有几个区别：
#   ① BaoStock 需要 login/logout（免费注册，但必须登录才能用）
#   ② BaoStock 能提供交易日历（AKShare 没有这个能力）
#   ③ BaoStock 的股票代码格式是 "sh.600519"（交易所前缀.纯代码）
#      而不是 "600519"（纯代码）或 "600519.SH"（Tushare 格式）
#
# 这个适配器的结构和 akshare.py 几乎一样：
#   - 底部工具函数 → 代码格式转换、数据解析
#   - 主类 BaoStockAdapter → fetch → normalize 两步走
#
# 阅读时可以和 akshare.py 对比着看——它们是同一个"模板"的不同实现。


# =============================================================================
# 工具函数
# =============================================================================


def _clean_text(value: Any) -> str | None:
    """清洗文本值，和 akshare.py 里的同名函数逻辑一致。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return None
    return text


def _parse_baostock_date(value: Any) -> date | None:
    """
    把 BaoStock 的日期字符串转为 Python date 对象。

    BaoStock 的日期格式比较统一（通常是 "2024-01-02"），
    所以这个函数比 _parse_date（akshare 版）更简单。
    """
    text = _clean_text(value)
    if text is None:
        return None
    return date.fromisoformat(text.replace("/", "-"))


def _split_baostock_code(code: str) -> tuple[str, str]:
    """
    拆分 BaoStock 格式的代码 → (纯代码, 交易所)。

    BaoStock 的代码格式： "sh.600519"、"sz.000001"、"bj.873001"
                                 ↑前缀.代码↑

    这个函数把它拆成两部分：
      _split_baostock_code("sh.600519") → ("600519", "SSE")
      _split_baostock_code("sz.000001") → ("000001", "SZSE")
      _split_baostock_code("bj.873001") → ("873001", "BSE")

    原理：
      "sh.600519".partition(".") → ("sh", ".", "600519")
      取第一段 = "sh" 查映射表 → "SSE"
      取第三段 = "600519" = 纯代码
    """
    # str.partition(sep) 返回三元组 (sep之前, sep本身, sep之后)
    exchange_code, _, symbol = code.partition(".")
    if not symbol:
        # 没有 "." 的情况：可能是纯代码（兜底处理）
        symbol = exchange_code
        exchange_code = ""

    # BaoStock 前缀 → 系统标准交易所代码 的映射
    exchange_map = {
        "sh": "SSE",    # 上海 (Shanghai)
        "sz": "SZSE",   # 深圳 (Shenzhen)
        "bj": "BSE",    # 北京 (Beijing)
    }
    return symbol, exchange_map.get(
        exchange_code.lower(),
        # 如果映射失败，靠代码前缀兜底推断
        "SSE" if symbol.startswith(("5", "6", "9")) else "SZSE",
    )


def _to_baostock_code(symbol: str, exchange: str | None) -> str:
    """
    把标准代码转成 BaoStock 格式：纯代码 + 交易所 → "前缀.纯代码"。

    这是 _split_baostock_code 的逆操作。

    示例：
      _to_baostock_code("600519", "SSE")  → "sh.600519"
      _to_baostock_code("000001", "SZSE") → "sz.000001"
      _to_baostock_code("873001", "BSE")  → "bj.873001"
    """
    # 系统标准代码 → BaoStock 前缀
    exchange_map = {
        "SSE": "sh",
        "SH": "sh",
        "SZSE": "sz",
        "SZ": "sz",
        "BSE": "bj",
        "BJ": "bj",
    }
    prefix = exchange_map.get((exchange or "").upper())

    # 如果交易所参数匹配不上，靠代码前缀推断
    if prefix is None:
        if symbol.startswith(("43", "83", "87", "88", "92")):
            prefix = "bj"
        elif symbol.startswith(("5", "6", "9")):
            prefix = "sh"
        else:
            prefix = "sz"

    return f"{prefix}.{symbol}"


def _result_set_to_records(result_set: Any) -> list[dict[str, Any]]:
    """
    把 BaoStock 的查询结果转成字典列表。

    BaoStock 的 API 返回的不是 pandas DataFrame，而是一个自定义的
    "ResultSet" 对象。它的用法像数据库游标（Cursor）：
      1. 获取字段名列表 → result_set.fields = ["code", "code_name", ...]
      2. 逐行读取      → result_set.next() + result_set.get_row_data()
      3. 把字段名和值"拉链"起来 → dict(zip(fields, values))

    zip() 函数的作用：
      就像拉链的两个齿，把两个列表一一配对。
      zip(["code", "name"], ["600519", "贵州茅台"]) → [("code", "600519"), ("name", "贵州茅台")]
      再套一层 dict() → {"code": "600519", "name": "贵州茅台"}

    示例流程：
      fields = ["code", "code_name"]
      第1行: values = ["sh.600519", "贵州茅台"]
             → dict(zip(fields, values)) → {"code": "sh.600519", "code_name": "贵州茅台"}
      第2行: values = ["sz.000001", "平安银行"]
             → {"code": "sz.000001", "code_name": "平安银行"}
    """
    # 获取列名（字段名列表）
    fields = list(getattr(result_set, "fields", []) or [])

    records: list[dict[str, Any]] = []
    # 逐行读取 —— 像翻书一样，一页一页翻
    while result_set.next():
        values = result_set.get_row_data()
        # zip + dict = "字段名 → 值" 的配对
        records.append(dict(zip(fields, values, strict=False)))

    return records


def _to_float(value: Any, *, default: float | None = None) -> float | None:
    """安全转浮点数。"""
    text = _clean_text(value)
    if text is None:
        return default
    return float(text)


# =============================================================================
# 主类：BaoStock 适配器
# =============================================================================


class BaoStockAdapter(StockDataSourceAdapter):
    """
    BaoStock（证券宝）数据源适配器。

    和 AKShare 的主要区别：
      ① 需要 login() / logout() — 免费但要"登录"
      ② 数据格式不同 — 代码是 "sh.600519" 而不是 "600519"
      ③ 多了交易日历 — 可以查到 A 股的开市/休市日期
      ④ 返回的是 ResultSet 而不是 pandas DataFrame
    """

    code = "baostock"
    name = "BaoStock"
    priority = 20         # 比 AKShare 低一点（AKShare=10），作为备选方案
    requires_token = False
    default_enabled = True

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def capabilities(self) -> AdapterCapability:
        """
        BaoStock 能做的事情比 AKShare 多一些：
          股票列表 ✓、日K线 ✓、交易日历 ✓
          但日K线只支持上交所和深交所（不支持北交所）。
        """
        return AdapterCapability(
            stock_list=True,
            daily_bars=True,
            calendars=True,  # ★ Baostock 独有优势：支持交易日历
            daily_bar_exchanges=("SSE", "SZSE"),  # 注意：比 AKShare 少 BSE
        )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_type="python_package",
            homepage_url="http://baostock.com/",
            docs_url="http://baostock.com/baostock/index.php/Python_API%E6%96%87%E6%A1%A3",
            auth_mode="none",
            stability="community",
            rate_limit_note="Uses BaoStock Python package APIs; login/logout is handled by the adapter.",
            install_note="Install optional package: pip install baostock.",
        )

    def health_check(self) -> HealthCheckResult:
        """
        检查 BaoStock 包是否安装、核心函数是否存在。
        核心函数：login、query_stock_basic（股票列表）、query_trade_dates（交易日历）。
        """
        try:
            client = self._get_client()
            # BaoStock 核心三件套：登录、查股票基本信息、查交易日
            if (
                not hasattr(client, "login")
                or not hasattr(client, "query_stock_basic")
                or not hasattr(client, "query_trade_dates")
            ):
                return HealthCheckResult(
                    healthy=False,
                    status="unhealthy",
                    message="BaoStock is installed, but required stock basic/calendar APIs were not found.",
                )
        except ModuleNotFoundError:
            return HealthCheckResult(
                healthy=False,
                status="unavailable",
                message="BaoStock is not installed. Install the optional baostock package to enable this source.",
            )
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, status="unhealthy", message=str(exc)
            )

        return HealthCheckResult(
            healthy=True, status="healthy", message="BaoStock package is available."
        )

    # ===== 获取股票列表 =====

    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        从 BaoStock 获取 A 股全部股票列表。

        和 AKShare 不同，BaoStock 需要先 login()，用完 logout()。
        这就像去图书馆：
          AKShare  = 开放式书架，直接拿就行
          BaoStock = 需要刷卡进门（login），走的时候也要刷卡（logout）

        另外，BaoStock 的 login 可能偶发失败，所以加了重试（最多 2 次）。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "BaoStock stock list adapter currently supports A_SHARE only."
            )

        client = self._get_client()
        errors: list[str] = []

        for attempt in range(1, 3):  # 最多重试 2 次
            # ---- 步骤 1：登录 ----
            login_result = client.login()
            # BaoStock 的 login 返回一个对象，error_code == "0" 表示成功
            if getattr(login_result, "error_code", "0") != "0":
                errors.append(
                    getattr(login_result, "error_msg", "BaoStock login failed.")
                )
                if attempt < 2:
                    sleep(1)
                    continue
                break  # 两次都失败，放弃

            try:
                # ---- 步骤 2：查询 ----
                result_set = client.query_stock_basic()
                if getattr(result_set, "error_code", "0") != "0":
                    raise RuntimeError(
                        getattr(
                            result_set,
                            "error_msg",
                            "BaoStock query_stock_basic failed.",
                        )
                    )
                return _result_set_to_records(result_set)
            except Exception as exc:
                errors.append(str(exc))
                if attempt < 2:
                    sleep(1)
                    continue
            finally:
                # ---- 步骤 3：无论如何都要登出 ----
                # finally 表示：不管 try 成功还是 except 异常，这段代码都会执行。
                # 这就保证了一定会 logout —— 避免占用 BaoStock 的连接资源。
                if hasattr(client, "logout"):
                    client.logout()

        raise RuntimeError(
            "; ".join(error for error in errors if error)
            or "BaoStock query_stock_basic failed."
        )

    def normalize_stock_list(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedStock]:
        """
        把 BaoStock 的原始股票数据转成统一格式。

        BaoStock 股票列表的关键字段：
          code      — 如 "sh.600519"（需要拆分成 symbol + exchange）
          code_name — 股票名称
          ipoDate   — 上市日期
          outDate   — 退市日期（如果已退市）
          status    — "1" = 上市中，"0" = 已退市

        注意：BaoStock 有 industry 和退市日期 —— AKShare 没有这些信息。
        这就是多数据源互补的好处。
        """
        normalized: list[NormalizedStock] = []

        for record in raw_records:
            raw_code = _clean_text(
                record.get("code") or record.get("证券代码")
            )
            name = _clean_text(
                record.get("code_name")
                or record.get("名称")
                or record.get("证券简称")
            )
            if raw_code is None or name is None:
                continue

            # 拆分 "sh.600519" → ("600519", "SSE")
            symbol, exchange = _split_baostock_code(raw_code)

            # 判断退市状态：BaoStock 中 status="0" 表示退市
            status = (
                "DELISTED"
                if str(record.get("status") or "").strip() == "0"
                else "LISTED"
            )

            normalized.append(
                NormalizedStock(
                    symbol=symbol,
                    exchange=exchange,
                    market="A_SHARE",
                    name=name,
                    status=status,
                    # AKShare 没有的字段，BaoStock 有：
                    industry=_clean_text(record.get("industry")),
                    listing_date=_parse_baostock_date(record.get("ipoDate")),
                    delisting_date=_parse_baostock_date(
                        record.get("outDate")
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
        从 BaoStock 获取某只股票的日K线数据。

        BaoStock 的 K 线 API：query_history_k_data_plus()

        关键参数：
          frequency="d"   → 日线（"w"=周线，"m"=月线）
          adjustflag="3"  → 不复权（"1"=后复权，"2"=前复权）
          fields="date,code,open,high,low,close,..." → 指定要哪些字段

        和 fetch_stock_list 一样需要 login/logout。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "BaoStock daily bars adapter currently supports A_SHARE only."
            )

        client = self._get_client()

        # 登录
        login_result = client.login()
        if getattr(login_result, "error_code", "0") != "0":
            raise RuntimeError(
                getattr(login_result, "error_msg", "BaoStock login failed.")
            )

        try:
            # 查询日K线
            result_set = client.query_history_k_data_plus(
                _to_baostock_code(symbol, exchange),  # 标准代码 → "sh.600519"
                "date,code,open,high,low,close,preclose,volume,amount,adjustflag",
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency="d",       # 日线
                adjustflag="3",      # 不复权
            )
            if getattr(result_set, "error_code", "0") != "0":
                raise RuntimeError(
                    getattr(
                        result_set,
                        "error_msg",
                        "BaoStock query_history_k_data_plus failed.",
                    )
                )
            return _result_set_to_records(result_set)
        finally:
            # 无论成功失败都要登出
            if hasattr(client, "logout"):
                client.logout()

    def normalize_daily_bars(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedDailyBar]:
        """
        把 BaoStock 的原始日K线转成统一格式。

        BaoStock 的日K线字段（和 AKShare 的区别）：
          - 有 preclose（前收盘价） —— AKShare 没有
          - code 是 "sh.600519" 格式 —— 需要拆分
          - date 是标准日期格式 —— 好解析
        """
        normalized: list[NormalizedDailyBar] = []

        for record in raw_records:
            raw_code = _clean_text(record.get("code"))
            trade_date = _parse_baostock_date(record.get("date"))

            if raw_code is None or trade_date is None:
                continue

            symbol, exchange = _split_baostock_code(raw_code)

            open_price = _to_float(record.get("open"))
            high = _to_float(record.get("high"))
            low = _to_float(record.get("low"))
            close = _to_float(record.get("close"))

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
                    pre_close=_to_float(record.get("preclose")),
                    # ★ BaoStock 有前收盘价（preclose），AKShare 这里是 None
                    volume=_to_float(record.get("volume"), default=0.0) or 0.0,
                    amount=_to_float(record.get("amount"), default=0.0) or 0.0,
                    adjust_factor=1.0,
                    adjust_type="none",
                    source=self.code,
                )
            )

        return normalized

    # ===== 获取交易日历（BaoStock 独有 AKShare 没有） =====

    def fetch_trading_calendar(
        self,
        *,
        market: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """
        获取 A 股交易日历。

        交易日历是什么？
          比如要知道"2024 年春节是哪几天休市"，
          就可以用交易日历来查。

        BaoStock 的 query_trade_dates() 返回指定日期范围内
        每一天是否开市的信息。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "BaoStock trading calendar adapter currently supports A_SHARE only."
            )

        client = self._get_client()

        login_result = client.login()
        if getattr(login_result, "error_code", "0") != "0":
            raise RuntimeError(
                getattr(login_result, "error_msg", "BaoStock login failed.")
            )

        try:
            if not hasattr(client, "query_trade_dates"):
                raise RuntimeError(
                    "BaoStock client does not expose query_trade_dates."
                )
            result_set = client.query_trade_dates(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
            if getattr(result_set, "error_code", "0") != "0":
                raise RuntimeError(
                    getattr(
                        result_set,
                        "error_msg",
                        "BaoStock query_trade_dates failed.",
                    )
                )
            return _result_set_to_records(result_set)
        finally:
            if hasattr(client, "logout"):
                client.logout()

    def normalize_trading_calendar(
        self,
        raw_records: list[dict[str, Any]],
        *,
        market: str,
    ) -> list[NormalizedTradingCalendar]:
        """
        把交易日历原始数据转成统一格式。

        BaoStock 的日历字段可能是：
          calendar_date / date  → 日期
          is_trading_day        → "1"（交易日） 或 "0"（休市）
        """
        normalized: list[NormalizedTradingCalendar] = []

        for record in raw_records:
            trade_date = _parse_baostock_date(
                record.get("calendar_date") or record.get("date")
            )
            if trade_date is None:
                continue

            raw_is_open = (
                str(
                    record.get("is_trading_day")
                    or record.get("is_open")
                    or ""
                )
                .strip()
                .lower()
            )

            normalized.append(
                NormalizedTradingCalendar(
                    market=market.upper(),
                    trade_date=trade_date,
                    # 支持多种表示方式：1, true, yes, y 都算交易日
                    is_open=raw_is_open in {"1", "true", "yes", "y"},
                    source=self.code,
                )
            )

        return normalized

    def _get_client(self) -> Any:
        """懒加载 BaoStock 模块。"""
        if self._client is None:
            self._client = import_module("baostock")
        return self._client
