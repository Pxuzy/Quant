from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any


# =============================================================================
# 【小白必读】base.py 是什么？
# =============================================================================
#
# 这个文件是整个适配器体系的"宪法"——它定义了：
#   ① 数据容器（dataclass）—— 统一的数据格式，所有适配器都必须输出这种格式
#   ② 抽象基类（ABC）      —— 规定了"一个适配器必须会做什么"
#
# 打个比方：
#   你在写一个"家电说明书模板"，规定了所有家电必须标注：电压、功率、插头类型。
#   具体到某个品牌（比如海尔冰箱），它得按照这个模板填写自己的参数。
#
#   base.py 就是这个模板：
#     - 数据容器 = 参数格式（电压写多少伏、功率写多少瓦）
#     - 抽象基类 = 必须填的项目（不能不填电压就去卖）
#
# 阅读顺序建议：
#   ① 先看数据容器（dataclass），理解"统一格式"长什么样
#   ② 再看抽象基类（ABC），理解"适配器必须实现哪些方法"


# =============================================================================
# 第一部分：数据容器（dataclass）—— "统一格式"
# =============================================================================
#
# @dataclass 是 Python 3.7+ 的一个装饰器，它的作用是：
#   自动生成 __init__、__repr__、__eq__ 等方法，让你少写一堆模板代码。
#
# 普通写法（要写 10+ 行）:
#   class Stock:
#       def __init__(self, symbol, name, ...):
#           self.symbol = symbol
#           self.name = name
#           ...
#
# dataclass 写法（1 行声明）:
#   @dataclass
#   class Stock:
#       symbol: str
#       name: str
#
# frozen=True 表示创建后不可修改（像元组一样），这很重要：
#   - 财经数据一旦获取就不该被修改
#   - 可以作为 dict 的 key 或放进 set 里（去重、缓存都用得到）
#   - 线程安全，多个地方同时读不会有问题


@dataclass(frozen=True)
class AdapterCapability:
    """
    描述一个适配器"能提供什么数据"。

    框架问："AKShare，你能干嘛？"
    AKShare 答："我能给股票列表、能给日K线，支持的交易所是上交所/深交所/北交所。"

    这就是 AdapterCapability 做的事 —— 一张能力清单。

    字段说明：
      stock_list           — 能不能提供股票列表？（True/False）
      daily_bars           — 能不能提供日K线数据？
      calendars            — 能不能提供交易日历？（比如哪天休市）
      daily_bar_exchanges  — 日K线支持哪些交易所？（SSE=上交所, SZSE=深交所, BSE=北交所）
                              None 表示"所有交易所都支持"
    """
    stock_list: bool
    daily_bars: bool = False
    calendars: bool = False
    daily_bar_exchanges: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, bool | list[str] | None]:
        """把能力清单转成字典，方便 JSON 输出给前端。"""
        return asdict(self)


@dataclass(frozen=True)
class ProviderMetadata:
    """
    数据源的"名片"——描述这个数据源的基本信息。

    字段说明：
      provider_type   — 数据源类型：
                         "python_package" = Python 包（如 akshare, baostock）
                         "node_package"   = Node.js 包（如 stock-sdk）
                         "external_api"   = 外部 API 服务
      homepage_url    — 官网地址
      docs_url        — 文档地址
      auth_mode       — 认证方式："none"（免费无需认证）/ "token"（需要 API Token）
      stability       — 稳定性级别：
                         "official" = 官方维护，商业级稳定
                         "community" = 社区维护，可能有 breaking change
      rate_limit_note — 频率限制说明（比如"每分钟最多 100 次请求"）
      install_note    — 安装说明（告诉用户 pip install 什么）
    """
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
    """
    健康检查的结果——告诉框架这个数据源能不能用。

    三个状态：
      "healthy"    — 一切正常，可以用
      "unavailable" — 包/Token 没装，不能用（但不是 bug）
      "unhealthy"  — 装了但出问题了（版本不兼容、函数缺失等）

    字段说明：
      healthy — True 表示可用，False 表示不可用
      status  — 状态标签（"healthy"/"unavailable"/"unhealthy"）
      message — 人类可读的说明（给用户看的，方便排查问题）
    """
    healthy: bool
    status: str
    message: str


@dataclass(frozen=True)
class NormalizedStock:
    """
    【核心数据结构】统一格式的股票信息。

    这是系统内部的"普通话"——不管数据来自 AKShare、BaoStock 还是 Tushare，
    最终都统一成这个格式。上层代码只认 NormalizedStock，不关心数据来源。

    字段说明：
      symbol         — 股票代码（纯数字，如 "600519"）
                       ★ 注意：不同数据源的代码格式不同
                       AKShare 直接用 "600519"
                       Tushare 用 "600519.SH"
                       BaoStock 用 "sh.600519"
                       适配器会统一处理成纯数字 "600519"

      exchange       — 交易所代码（"SSE"=上交所 / "SZSE"=深交所 / "BSE"=北交所）

      market         — 市场类型（"A_SHARE"=A股，"HK"=港股，"US"=美股）

      name           — 股票名称（如 "贵州茅台"、"平安银行"）

      status         — 上市状态：
                       "LISTED"    = 正常上市
                       "DELISTED"  = 已退市
                       "SUSPENDED" = 暂停上市

      industry       — 所属行业（如 "白酒"、"银行"），None 表示不知道

      listing_date   — 上市日期（Python date 对象）

      delisting_date — 退市日期，None 表示还在上市

      source         — 数据来源标识（"akshare"/"baostock"/"tushare"……）
                       用于追溯数据来源，方便排查问题
    """
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
    """
    【核心数据结构】统一格式的日K线数据。

    日K线 = 一只股票一天的交易数据。

    OHLC 是什么？
      这是量化领域最基础的四个价格，几乎所有的技术分析都基于它们：
        O = Open   = 开盘价（交易日第一笔成交价）
        H = High   = 最高价（当天最高成交价）
        L = Low    = 最低价（当天最低成交价）
        C = Close  = 收盘价（交易日最后一笔成交价）

    一根蜡烛图（K线图）就是由这四个价格画出来的。

    字段说明：
      symbol        — 股票代码
      exchange      — 交易所
      market        — 市场类型
      trade_date    — 交易日期

      open          — 开盘价
      high          — 最高价
      low           — 最低价
      close         — 收盘价
      pre_close     — 前收盘价（Tushare 和 BaoStock 提供，AKShare 不提供）

      volume        — 成交量（股）
      amount        — 成交额（元）

      adjust_factor — 复权因子（不复权时 = 1.0）
                      复权是什么？股票分红送股后，股价会突然"打折"。
                      复权就是把历史价格按比例调整，消除这种跳变。
                      不复权 = 用原始价格（adjust_factor=1.0）

      adjust_type   — 复权类型：
                       "none"         = 不复权
                       "qfq"          = 前复权（forward-adjusted）
                       "hfq"          = 后复权（backward-adjusted）

      source        — 数据来源

      ingested_at   — 数据入库时间（自动填当前 UTC 时间）
                      注意：这个字段不是数据源给的，是系统自己加上的时间戳
    """
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
    # field(default_factory=...) 表示每次创建对象时会调用一次指定的函数
    # 这样不同 NormalizedDailyBar 的 ingested_at 可能差几毫秒，各自独立
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class NormalizedTradingCalendar:
    """
    【核心数据结构】统一格式的交易日历。

    什么是交易日历？
      A 股不是每天都交易的：周六周日、春节、国庆等都休市。
      交易日历就是告诉你"这一天开不开市"。

    字段说明：
      market     — 市场类型
      trade_date — 日期
      is_open    — 是否开市（True=交易日，False=休市日）
      source     — 数据来源
    """
    market: str
    trade_date: date
    is_open: bool
    source: str


# =============================================================================
# 第二部分：抽象基类（ABC）—— "接口约定"
# =============================================================================
#
# ABC = Abstract Base Class（抽象基类）
#
# 它的作用就一句话：你不能直接说"随便什么适配器"，
# 你必须说"一个实现了这些方法的适配器"。ABC 就是那个"这些方法"的清单。
#
# 类比：你不能招一个"会干活的人"，你只能招"会 Python + 会 SQL + 会 Excel 的人"。
# ABC 就是那个职位描述。
#
# @abstractmethod 表示"子类必须实现这个方法，否则不能实例化"。
# 如果继承这个类却没有实现被 @abstractmethod 标记的方法，
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
