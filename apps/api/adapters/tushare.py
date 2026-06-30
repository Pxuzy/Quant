from __future__ import annotations

import logging
import os
from datetime import date
from importlib import import_module
from typing import Any

logger = logging.getLogger(__name__)

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    NormalizedTradingCalendar,
    ProviderMetadata,
    StockDataSourceAdapter,
    normalize_daily_bar_adjust_type,
)


# =============================================================================
# 【小白必读】tushare.py 是什么？
# =============================================================================
#
# Tushare 是国内最流行的 Python 金融数据库之一。
# 和 AKShare/BaoStock 的关键区别：
#   ① 需要注册获取 API Token（https://tushare.pro 注册后免费）
#   ② Token 通过环境变量 TUSHARE_TOKEN 或构造函数传入
#   ③ 数据质量较高、字段丰富（有 industry、pre_close 等）
#   ④ 有频率限制（根据账号等级不同）
#   ⑤ 代码格式是 "600519.SH"（代码.后缀）
#
# 这个适配器的结构和其他适配器完全一致，
# 唯一特别的是 token 管理部分。


# =============================================================================
# 工具函数
# =============================================================================


def _clean_text(value: Any) -> str | None:
    """清洗文本值。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return None
    return text


def _parse_tushare_date(value: Any) -> date | None:
    """
    解析 Tushare 的日期格式。

    Tushare 的日期通常是 "20240102"（8 位纯数字），
    也可能是 "2024-01-02" 或 "2024/01/02"。
    """
    text = _clean_text(value)
    if text is None:
        return None
    digits = text.replace("-", "").replace("/", "")
    if len(digits) == 8 and digits.isdigit():
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    return date.fromisoformat(text.replace("/", "-"))


def _split_tushare_code(ts_code: str) -> tuple[str, str]:
    """
    拆分 Tushare 格式的代码 → (纯代码, 交易所)。

    Tushare 的代码格式： "600519.SH"、"000001.SZ"、"873001.BJ"
                                 ↑代码.后缀↑

    后缀含义：
      SH = 上海 (Shanghai)
      SZ = 深圳 (Shenzhen)
      BJ = 北京 (Beijing)

    _split_tushare_code("600519.SH") → ("600519", "SSE")
    _split_tushare_code("000001.SZ") → ("000001", "SZSE")
    _split_tushare_code("873001.BJ") → ("873001", "BSE")
    """
    symbol, _, suffix = ts_code.partition(".")

    # Tushare 后缀 → 系统标准交易所代码
    exchange_map = {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
    }

    return symbol, exchange_map.get(
        suffix.upper(),
        # 映射失败时靠代码前缀推断
        "SSE" if symbol.startswith(("5", "6", "9")) else "SZSE",
    )


def _to_tushare_code(symbol: str, exchange: str | None) -> str:
    """
    把标准代码转成 Tushare 格式：纯代码 + 交易所 → "代码.后缀"。

    这是 _split_tushare_code 的逆操作。

    示例：
      _to_tushare_code("600519", "SSE")  → "600519.SH"
      _to_tushare_code("000001", "SZSE") → "000001.SZ"
      _to_tushare_code("873001", "BSE")  → "873001.BJ"
    """
    suffix_map = {
        "SSE": "SH",
        "SH": "SH",
        "SZSE": "SZ",
        "SZ": "SZ",
        "BSE": "BJ",
        "BJ": "BJ",
    }
    suffix = suffix_map.get((exchange or "").upper())

    if suffix is None:
        # 靠代码前缀推断
        if symbol.startswith(("43", "83", "87", "88", "92")):
            suffix = "BJ"
        elif symbol.startswith(("5", "6", "9")):
            suffix = "SH"
        else:
            suffix = "SZ"

    return f"{symbol}.{suffix}"


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    """把 pandas DataFrame 转成字典列表，和 akshare.py 逻辑一致。"""
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    if isinstance(frame, list):
        return [record for record in frame if isinstance(record, dict)]
    raise TypeError("Tushare returned an unsupported stock-list payload.")


def _to_float(value: Any, *, default: float | None = None) -> float | None:
    """安全转浮点数。"""
    text = _clean_text(value)
    if text is None:
        return default
    return float(text)


# =============================================================================
# 主类：Tushare 适配器
# =============================================================================


class TushareAdapter(StockDataSourceAdapter):
    """
    Tushare 数据源适配器。

    特点：
      - 需要 API Token（在 https://tushare.pro 注册获取）
      - Token 支持两种配置方式：
          ① 环境变量 TUSHARE_TOKEN
          ② 构造参数 token="xxx"
      - 数据质量较高，返回 pandas DataFrame
      - 有交易日历功能
      - 代码格式是 "600519.SH"（代码.后缀）
    """

    code = "tushare"
    name = "Tushare"
    priority = 30          # 优先级低于免费源，因为有门槛
    requires_token = True   # ★ 需要 Token
    default_enabled = False # ★ 默认不启用（用户需要先配 Token）

    def __init__(
        self, *, client: Any | None = None, token: str | None = None
    ) -> None:
        """
        初始化 Tushare 适配器。

        参数 token 是可选的：如果没传，会从环境变量 TUSHARE_TOKEN 读取。
        """
        self._client = client
        self._token = token

    def capabilities(self) -> AdapterCapability:
        """Tushare 功能比较全：股票列表、日K线、交易日历都有。"""
        return AdapterCapability(
            stock_list=True,
            daily_bars=True,
            calendars=True,
            daily_bar_exchanges=("SSE", "SZSE", "BSE"),
        )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_type="python_package",
            homepage_url="https://tushare.pro/",
            docs_url="https://tushare.pro/document/1?doc_id=108",
            auth_mode="token",
            stability="official",  # ★ Tushare 是官方维护的，比社区源更稳定
            rate_limit_note=(
                "Requires a Tushare Pro token and follows Tushare account quota limits; "
                "industry and sector datasets may require additional points or package permissions."
            ),
            install_note="Install optional package: pip install tushare. Set TUSHARE_TOKEN before enabling.",
            mcp_url="https://tushare.pro/document/1?doc_id=463",
            mcp_role="adapter_layer",
            sector_capabilities=(
                "index_classify",
                "index_member_all",
                "index_weight",
                "ths_hot",
            ),
        )

    def auth_status(self) -> str:
        """
        检查 Token 配置状态。

        返回：
          "configured" = Token 已配置（可以通过构造函数传，也可以通过环境变量）
          "missing"    = Token 没配
        """
        return (
            "configured"
            if self._token or os.getenv("TUSHARE_TOKEN")
            else "missing"
        )

    def health_check(self) -> HealthCheckResult:
        """检查 Tushare 包是否安装、Token 是否配置。"""
        try:
            self._get_client()
        except ModuleNotFoundError:
            return HealthCheckResult(
                healthy=False,
                status="unavailable",
                message="Tushare is not installed. Install the optional tushare package to enable this source.",
            )
        except RuntimeError as exc:
            # Token 没配的情况
            logger.warning("Tushare token not configured: %s", exc)
            return HealthCheckResult(
                healthy=False, status="unavailable", message=str(exc)
            )
        except Exception as exc:
            logger.warning("Tushare health check failed: %s", exc)
            return HealthCheckResult(
                healthy=False, status="unhealthy", message=str(exc)
            )

        return HealthCheckResult(
            healthy=True,
            status="healthy",
            message="Tushare package and token are available.",
        )

    # ===== 获取股票列表 =====

    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        从 Tushare 获取 A 股全部股票列表。

        Tushare 的 API 风格和 AKShare 不同：
          - 用 client.stock_basic() 而非多个备选函数
          - 需要指定 fields（要哪些字段）
          - 返回 pandas DataFrame
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "Tushare stock list adapter currently supports A_SHARE only."
            )

        client = self._get_client()
        frame = client.stock_basic(
            exchange="",         # 空 = 所有交易所
            list_status="L",     # L = Listed（上市中）
            fields="ts_code,symbol,name,area,industry,list_date",
            # ts_code    = Tushare 格式代码（如 "600519.SH"）
            # symbol     = 纯代码（如 "600519"）
            # name       = 股票名称
            # area       = 地区
            # industry   = 行业
            # list_date  = 上市日期
        )
        return _records_from_frame(frame)

    def normalize_stock_list(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedStock]:
        """
        把 Tushare 的原始股票数据转成统一格式。

        Tushare 的股票列表数据质量比 AKShare 高：
          - 有行业信息（industry）
          - 有明确的 ts_code 和 symbol 分离
          - 字段名是英文（规范）
        """
        normalized: list[NormalizedStock] = []

        for record in raw_records:
            ts_code = _clean_text(record.get("ts_code"))
            name = _clean_text(record.get("name"))
            if ts_code is None or name is None:
                continue

            # 拆分 "600519.SH" → ("600519", "SSE")
            symbol, exchange = _split_tushare_code(ts_code)

            normalized.append(
                NormalizedStock(
                    symbol=symbol,
                    exchange=exchange,
                    market="A_SHARE",
                    name=name,
                    status="LISTED",
                    industry=_clean_text(record.get("industry")),
                    # ★ Tushare 有行业信息，AKShare 没有
                    listing_date=_parse_tushare_date(
                        record.get("list_date")
                    ),
                    delisting_date=None,
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
        从 Tushare 获取日K线数据。

        用 client.daily()，返回 pandas DataFrame。
        Tushare 只接受 "YYYYMMDD" 格式的日期（用 strftime 转换）。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "Tushare daily bars adapter currently supports A_SHARE only."
            )
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        if adjust_type_code != "none":
            raise ValueError("Tushare daily bars adapter currently supports unadjusted bars only.")

        client = self._get_client()
        frame = client.daily(
            ts_code=_to_tushare_code(symbol, exchange),
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        return _records_from_frame(frame)

    def normalize_daily_bars(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedDailyBar]:
        """
        把 Tushare 原始日K线转成统一格式。

        Tushare 的日K线字段（注意和 AKShare 的差异）：
          ts_code    → "600519.SH"（需要拆分）
          trade_date → "20240102"（8 位数字）
          vol        → 成交量（Tushare 用 "vol"，不是 "volume"）
          pre_close  → 前收盘价（AKShare 没有这个字段）
        """
        normalized: list[NormalizedDailyBar] = []

        for record in raw_records:
            ts_code = _clean_text(record.get("ts_code"))
            trade_date = _parse_tushare_date(record.get("trade_date"))
            if ts_code is None or trade_date is None:
                continue

            symbol, exchange = _split_tushare_code(ts_code)

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
                    pre_close=_to_float(record.get("pre_close")),
                    # ★ Tushare 支持前收盘价
                    volume=_to_float(record.get("vol"), default=0.0) or 0.0,
                    # ★ 注意 Tushare 用 "vol" 而不是 "volume"
                    amount=_to_float(record.get("amount"), default=0.0) or 0.0,
                    adjust_factor=1.0,
                    adjust_type="none",
                    source=self.code,
                )
            )

        return normalized

    # ===== 获取交易日历 =====

    def fetch_trading_calendar(
        self,
        *,
        market: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """
        获取 A 股交易日历。

        Tushare 用 client.trade_cal()，返回每天是否开市。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "Tushare trading calendar adapter currently supports A_SHARE only."
            )

        client = self._get_client()
        frame = client.trade_cal(
            exchange="",  # 空 = 所有交易所
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields="cal_date,is_open",
        )
        return _records_from_frame(frame)

    def normalize_trading_calendar(
        self,
        raw_records: list[dict[str, Any]],
        *,
        market: str,
    ) -> list[NormalizedTradingCalendar]:
        """把交易日历原始数据转成统一格式。"""
        normalized: list[NormalizedTradingCalendar] = []

        for record in raw_records:
            trade_date = _parse_tushare_date(
                record.get("cal_date") or record.get("trade_date")
            )
            if trade_date is None:
                continue

            raw_is_open = (
                str(record.get("is_open") or "").strip().lower()
            )

            normalized.append(
                NormalizedTradingCalendar(
                    market=market.upper(),
                    trade_date=trade_date,
                    is_open=raw_is_open in {"1", "true", "yes", "y"},
                    source=self.code,
                )
            )

        return normalized

    def _get_client(self) -> Any:
        """
        获取 Tushare 客户端 —— 包含 Token 管理逻辑。

        这是所有适配器中最复杂的 _get_client —— 因为要处理 Token。

        流程：
          ① 如果已经初始化过，直接返回（缓存）
          ② 读取 Token：优先构造参数，没有则读环境变量
          ③ 导入 tushare 包，设置 Token，创建 pro_api 对象
        """
        if self._client is not None:
            return self._client

        # 优先用构造函数传入的 token，没有则从环境变量读
        token = self._token or os.getenv("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError(
                "TUSHARE_TOKEN is not configured. Tushare remains disabled until a token is provided."
            )

        tushare = import_module("tushare")

        # Tushare 的旧版 API 需要 set_token，新版 pro_api 直接传 token
        if hasattr(tushare, "set_token"):
            tushare.set_token(token)

        # pro_api(token) 是 Tushare 的推荐用法
        self._client = tushare.pro_api(token)
        return self._client
