from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AdapterCapability:
    """Adapter capability: what data this source can provide."""
    stock_list: bool
    daily_bars: bool = False
    calendars: bool = False
    daily_bar_exchanges: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, bool | list[str] | None]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderMetadata:
    """Provider metadata: name, type, URLs, auth requirements."""
    provider_type: str
    homepage_url: str | None = None
    docs_url: str | None = None
    auth_mode: str = "none"
    stability: str = "community"
    rate_limit_note: str | None = None
    install_note: str | None = None
    mcp_url: str | None = None
    mcp_role: str | None = None
    sector_capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HealthCheckResult:
    """Health check result with status and message."""
    healthy: bool
    status: str
    message: str


@dataclass(frozen=True)
class NormalizedStock:
    """Unified stock record. All adapters normalize to this format."""
    symbol: str
    exchange: str
    market: str
    name: str
    status: str
    industry: str | None
    listing_date: date | None
    delisting_date: date | None
    source: str


@dataclass(frozen=True)
class NormalizedDailyBar:
    """Unified daily bar (OHLCV) record."""
    symbol: str
    exchange: str
    market: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float | None
    volume: float
    amount: float
    adjust_factor: float | None
    source: str
    adjust_type: str = "none"
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class NormalizedTradingCalendar:
    """Unified trading calendar record."""
    market: str
    trade_date: date
    is_open: bool
    source: str


class StockDataSourceAdapter(ABC):
    """Abstract base for all data source adapters.

    Each adapter must implement: capabilities, metadata, health_check,
    plus at least one data-fetch method (stock_list / daily_bars / calendars).
    """
# Python 会在创建对象时直接报错，而不是等到调用时才出错。
# 这叫做"在编译/加载阶段就发现问题，而不是运行时才爆炸"。


class StockDataSourceAdapter(ABC):
    """
    股票数据源适配器的抽象基类 —— 所有适配器的"接口约定"。

    子类必须实现什么？
      - capabilities()         → 告诉框架你能做什么
      - health_check()         → 检查你是否可用
      - fetch_stock_list()     → 获取原始股票列表
      - normalize_stock_list() → 把原始列表转成统一格式

    子类可选实现什么？
      - fetch_daily_bars()       → 获取日K线（默认抛 NotImplementedError）
      - normalize_daily_bars()   → 归一化日K线
      - fetch_trading_calendar() → 获取交易日历
      - normalize_trading_calendar() → 归一化交易日历

    设计模式：模板方法模式（Template Method Pattern）
      框架层面定义好 fetch → normalize 两步走的流程，
      每个子类只需要填具体的实现。调用的节奏由框架控制。
    """

    # ===== 类级别属性（子类必须覆盖） =====

    code: str               # 适配器唯一标识符，如 "akshare"、"baostock"
    name: str               # 人类可读的名称，如 "AKShare"、"BaoStock"
    priority: int = 100     # 优先级（数字越小越优先）
                            #  10 = AKShare（免费优先）
                            #  20 = BaoStock
                            #  25 = AData
                            #  30 = Tushare（需要 Token）
                            #  45 = Stock SDK（实验性）
                            # 框架按 priority 排序返回，
                            # 上层代码优先尝试 priority 小的适配器
    requires_token: bool = False   # 是否需要 API Token（Tushare 需要，AKShare 不要）
    default_enabled: bool = True   # 默认是否启用（Tushare/StockSDK 默认关闭）

    # ===== 元信息（子类通常需要覆盖） =====

    def metadata(self) -> ProviderMetadata:
        """
        返回数据源的元信息。子类可以覆盖来提供更详细的信息。

        默认实现只是根据 requires_token 判断认证方式。
        """
        return ProviderMetadata(
            provider_type="external_api",
            auth_mode="token" if self.requires_token else "none",
        )

    def auth_status(self) -> str:
        """
        检查认证状态。

        返回值：
          "not_required" — 不需要认证（免费数据源）
          "configured"   — Token 已配置
          "missing"      — 需要 Token 但没配
          "unknown"      — 需要 Token，但不确定配没配
        """
        return "unknown" if self.requires_token else "not_required"

    # ===== 必须实现的方法（@abstractmethod） =====
    #
    # 这 4 个方法 = 一个适配器的最低门槛。
    # 为什么恰恰是这 4 个？
    #   系统中"展示股票列表"是最基本的功能，
    #   fetch_stock_list + normalize_stock_list 是提供这一功能的完整链路。
    #   health_check + capabilities 是让框架知道适配器能不能用、能用在哪。
    #   所以把门槛设在这里：只要能提供股票列表就算一个合法适配器。
    #   日K线和交易日历是可选的 —— 有些免费数据源只提供列表。
    #

    @abstractmethod
    def capabilities(self) -> AdapterCapability:
        """
        返回适配器的能力清单。

        框架启动时会调这个方法，收集所有适配器的能力，
        然后根据用户请求来决定用哪个适配器。
        比如用户要日K线，框架就找 daily_bars=True 的适配器。
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> HealthCheckResult:
        """
        检查适配器当前是否可用。

        框架会在启动时/定期调用，如果返回 unhealthy，
        就把这个适配器标记为不可用，后续请求跳过它。
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        获取原始股票列表。

        参数 market 是市场类型（如 "A_SHARE"），
        * 表示后面的参数必须用关键字传，不能按位置传。
        这个设计是为了代码可读性 ——
          调用方必须写 adapter.fetch_stock_list(market="A_SHARE")
          而不能写 adapter.fetch_stock_list("A_SHARE")

        返回值是原始字典列表 —— 还没有归一化。
        因为每个数据源的字段名不同（中文/英文），
        先拿原始数据，再走 normalize 统一格式。
        """
        raise NotImplementedError

    @abstractmethod
    def normalize_stock_list(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedStock]:
        """
        把原始股票列表转成统一格式。

        "归一化"（normalize）的意思：
          不同数据源的字段五花八门：
            AKShare:   {"代码": "000001", "名称": "平安银行"}
            Tushare:   {"ts_code": "000001.SZ", "name": "平安银行"}
            BaoStock:  {"code": "sz.000001", "code_name": "平安银行"}

          归一化后:
            NormalizedStock(symbol="000001", exchange="SZSE", name="平安银行")

          不管原始数据长什么样，输出都是同一个格式。
          上层代码只需要知道 NormalizedStock，不需要知道数据来源。
        """
        raise NotImplementedError

    # ===== 可选实现的方法（有默认行为：抛 NotImplementedError） =====
    #
    # 这些方法没有 @abstractmethod，但默认行为是 raise NotImplementedError。
    # 区别是什么？
    #   @abstractmethod → 不实现就不能实例化（硬约束）
    #   raise NotImplementedError → 可以实例化，但调用时会报错（软约束）
    #
    # 为什么这样做？
    #   日K线和交易日历是"加分项"，不是"入场券"。
    #   有的免费数据源只能提供股票列表，不能提供日K线。
    #   所以让子类自己选择——有能力就实现，没能力就算了。
    #   框架在调用前会先检查 capabilities()，不会乱调。
    #

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
        获取某只股票在某个日期范围内的日K线原始数据。

        参数说明：
          symbol     — 股票代码（如 "600519"）
          exchange   — 交易所代码（如 "SSE"），可能为 None
          market     — 市场类型（如 "A_SHARE"）
          start_date — 开始日期（含）
          end_date   — 结束日期（含）
        """
        raise NotImplementedError

    def normalize_daily_bars(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedDailyBar]:
        """把原始日K线数据转成统一格式。"""
        raise NotImplementedError

    def fetch_trading_calendar(
        self,
        *,
        market: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """获取交易日历原始数据。"""
        raise NotImplementedError

    def normalize_trading_calendar(
        self, raw_records: list[dict[str, Any]], *, market: str
    ) -> list[NormalizedTradingCalendar]:
        """把原始交易日历转成统一格式。"""
        raise NotImplementedError
