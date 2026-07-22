from __future__ import annotations

import logging
from datetime import date
from importlib import import_module
from inspect import signature
from time import sleep
from typing import Any

logger = logging.getLogger(__name__)

from backend.app.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    ProviderMetadata,
    StockDataSourceAdapter,
    normalize_daily_bar_adjust_type,
)

# =============================================================================
# 【小白必读】这个文件在做什么？
# =============================================================================
#
# 这是一个"适配器"（Adapter）——它就像电源转换插头：
#   中国的插座 <--转换插头--> 欧洲的电器
#   我们的系统 <--适配器--> AKShare数据源
#
# AKShare 是一个开源的 Python 金融数据库，能免费获取 A 股数据。
# 但 AKShare 返回的数据格式是它自己的风格（字段名可能是中文，结构各异），
# 而我们的系统需要统一的格式（英文字段名、固定结构）。
#
# 适配器的工作就是：把 AKShare 的"方言"翻译成系统的"普通话"。
#
# 文件结构（阅读顺序）：
#   ① 底部工具函数（_开头）= 螺丝刀、扳手，给主类用的
#   ② AkShareAdapter 主类 = 转换插头本身
#   ③ 两个全局解析函数 _parse_date / _to_float
#
# 对于这篇文章中更详细的讲解，请查看同目录下的 base.py：
#   - StockDataSourceAdapter（父类，定义了"适配器必须会做什么"）
#   - NormalizedStock / NormalizedDailyBar（统一格式的数据结构）


# =============================================================================
# 第一部分：工具函数 —— 小而专一，每个只做一件事
# =============================================================================
# 这类函数都以 _ 开头，Python 约定表示"模块内部使用，别从外面直接调"。
# 它们的存在是因为很多地方要做同样的小操作（清洗数据、猜交易所……），
# 抽成函数避免到处复制粘贴。


def _clean_text(value: Any) -> str | None:
    """
    清洗一个值，返回干净的字符串，或者返回 None。

    为什么要这个函数？
      AKShare 返回的数据里，空值可能是 None、空字符串 ""、横杠 "-" 或 "--"。
      如果每次都手写判断，代码会又臭又长，所以封装成一个函数。

    示例：
      _clean_text(None)   → None       （空值）
      _clean_text("  ")   → None       （全是空格）
      _clean_text("-")    → None       （数据源用横杠表示"没有"）
      _clean_text("--")   → None       （同上）
      _clean_text(" 平安 ") → "平安"    （去掉首尾空格）
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return None
    return text


def _infer_exchange(symbol: str) -> str:
    """
    根据股票代码推断它属于哪个交易所。

    中国的 A 股分三个交易所：
      - SSE  (上海证券交易所) — 代码以 5、6、9 开头，如 600519（贵州茅台）
      - SZSE (深圳证券交易所) — 代码以 0、2、3 开头，如 000001（平安银行）
      - BSE  (北京证券交易所) — 代码以 43、83、87、88、92 开头

    AKShare 返回的数据里有时没有"交易所"字段，所以需要靠代码前缀来猜。

    示例：
      _infer_exchange("600519") → "SSE"   （6 开头 → 上海）
      _infer_exchange("000001") → "SZSE"  （0 开头 → 深圳）
      _infer_exchange("873001") → "BSE"   （87 开头 → 北京）
    """
    # Python 的 str.startswith() 可以接收元组，一次检查多个前缀
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return "BSE"  # 北京证券交易所 (Beijing Stock Exchange)
    if symbol.startswith(("5", "6", "9")):
        return "SSE"  # 上海证券交易所 (Shanghai Stock Exchange)
    return "SZSE"  # 深圳证券交易所 (Shenzhen Stock Exchange) — 默认


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    """
    把 AKShare 返回的数据转成 Python 字典列表。

    背景知识：
      AKShare 底层用 pandas（Python 的数据分析库）的 DataFrame 来存数据。
      DataFrame 就像一张 Excel 表格，有行有列。
      但我们后续处理需要的是字典列表 —— 每一行变成一个 dict，列名变 key。

    示例：
      DataFrame:                    转换后:
      ┌──────┬──────┐              [ {"名称": "平安银行", "代码": "000001"},
      │ 名称   │ 代码   │               {"名称": "万科A",   "代码": "000002"} ]
      ├──────┼──────┤
      │平安银行│000001│
      │万科A  │000002│
      └──────┴──────┘

    这个函数兼容两种输入：
      ① pandas DataFrame（有 to_dict 方法）→ 用 orient="records" 转换
      ② 已经是 list 的 → 直接筛选出其中的 dict 元素
    """
    # 情况一：输入是 DataFrame（pandas 对象）
    if hasattr(frame, "to_dict"):
        # orient="records" 的意思是：每行变成一个 dict
        # 例如 [{"名称": "平安", "代码": "000001"}, {"名称": "万科", "代码": "000002"}]
        records = frame.to_dict(orient="records")
        if isinstance(records, list):
            # 过滤掉不是 dict 的元素（防御性编程，正常不会出现）
            return [record for record in records if isinstance(record, dict)]

    # 情况二：输入已经是 list（某些 AKShare 函数直接返回 list）
    if isinstance(frame, list):
        return [record for record in frame if isinstance(record, dict)]

    # 既不是 DataFrame 也不是 list → 不知道怎么处理，报错
    raise TypeError("AKShare returned an unsupported stock-list payload.")


def _records_with_symbol(frame: Any, symbol: str) -> list[dict[str, Any]]:
    """
    和 _records_from_frame 一样，但会给每条记录补上 symbol 字段。

    为什么需要这个？
      某些 AKShare 函数（如 stock_zh_a_daily）返回的数据里没有股票代码字段。
      但后面的 normalize_daily_bars 需要用到 symbol，所以在这里提前补上。

    示例：
      _records_with_symbol(df, "000001")
      → [{"date": "2024-01-02", "close": 10.5, "symbol": "000001"}, ...]
                       原来没有 symbol ↑                这里补上了 ↑
    """
    records = _records_from_frame(frame)
    for record in records:
        # setdefault: 如果 key 不存在就设默认值；如果已存在则不动
        # 这样即使 AKShare 字段里已经有 symbol，也不会被覆盖
        record.setdefault("symbol", symbol)
    return records


def _to_sina_symbol(symbol: str, exchange: str | None) -> str:
    """
    把标准股票代码转换成新浪财经 API 的格式。

    不同数据源对股票代码的命名规则不同：
      我们的系统：  "600519" + 交易所="SSE"
      AKShare 某些函数需要： "sh600519"（新浪格式）
                          ↑ sh=上海, sz=深圳, bj=北京

    这个函数做的就是拼接前缀的工作。

    示例：
      _to_sina_symbol("600519", "SSE")  → "sh600519"
      _to_sina_symbol("000001", "SZSE") → "sz000001"
      _to_sina_symbol("873001", "BSE")  → "bj873001"
    """
    exchange_code = (exchange or "").upper()

    # 方式一：根据传入的交易所参数（优先使用）
    if exchange_code in {"SSE", "SH"}:
        return f"sh{symbol}"
    if exchange_code in {"BSE", "BJ"}:
        return f"bj{symbol}"
    if exchange_code in {"SZSE", "SZ"}:
        return f"sz{symbol}"

    # 方式二：如果没传交易所参数，根据代码前缀推断（兜底逻辑）
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return f"bj{symbol}"
    if symbol.startswith(("5", "6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


def _try_fetch(candidates: list[tuple[str, Any]], *, attempts: int = 2) -> list[dict[str, Any]]:
    """
    按顺序尝试多个数据获取方法，失败就换下一个，都失败则报错。

    为什么需要这个？
      ① AKShare 版本迭代快，某些函数可能改名或废弃。准备多个备选方案
         （如 stock_info_a_code_name 和 stock_zh_a_spot_em），哪个好用哪个。
      ② 网络请求可能偶发失败，每个方法自动重试（默认 2 次）。

    参数说明：
      candidates: [(方法名, 调用函数), ...]
                  例如 [("方案A", lambda: client.func_a()),
                        ("方案B", lambda: client.func_b())]
      attempts:   每个方法最多试几次（默认 2 次）

    示例流程：
      方案A 第1次 → 失败（网络超时）→ 等1秒 → 方案A 第2次 → 成功 ✓
      如果方案A两次都失败 → 换方案B → 同上流程
      所有方案都失败 → 抛出 RuntimeError，里面包含所有错误信息
    """
    errors: list[str] = []
    for name, fetcher in candidates:
        for attempt in range(1, attempts + 1):
            try:
                return fetcher()
            except Exception as exc:
                # 记录每次失败的信息，方便调试
                logger.debug("AKShare %s attempt %d failed: %s", name, attempt, exc)
                errors.append(f"{name} attempt {attempt}: {exc}")
                if attempt < attempts:
                    # 重试前等 1 秒，避免短时间内反复冲击服务器
                    sleep(1)
    # 所有备选方案都失败了 → 把收集到的错误一次性报出来
    raise RuntimeError("; ".join(errors))


def _supports_parameter(func: Any, parameter: str) -> bool:
    """
    检查一个函数是否支持某个参数。

    为什么需要这个？
      AKShare 不同版本中，同一个函数的参数可能不一样。
      比如 stock_zh_a_hist 在旧版本没有 timeout 参数，新版本有。
      用这个函数探测一下，有就传，没有就不传，避免报错。

      Python 的 inspect.signature() 可以读取函数的参数签名，
      就像看说明书一样知道这个函数接受哪些参数。

    示例：
      def foo(a, b): ...
      def bar(a, b, timeout=10): ...

      _supports_parameter(foo, "timeout")  → False  （foo 没有 timeout）
      _supports_parameter(bar, "timeout")  → True   （bar 有 timeout）
    """
    try:
        return parameter in signature(func).parameters
    except (TypeError, ValueError):
        # 某些特殊对象（如 C 扩展、内置函数）可能没有签名
        # 这种情况保守处理：假装不支持，不传这个参数
        return False


# =============================================================================
# 第二部分：主菜 —— AKShare 适配器类
# =============================================================================
#
# 设计模式：适配器模式（Adapter Pattern）
#   父类 StockDataSourceAdapter 定义了一组"接口"（必须实现的方法）
#   子类 AkShareAdapter 负责具体的实现
#
# 这样做的好处：
#   当你需要接入新的数据源（比如 Wind、东方财富），只需写一个新的 Adapter 子类，
#   系统其他部分不用改动 —— 因为它们只认"接口"，不关心具体是谁实现的。
#   这叫做"面向接口编程，而不是面向实现编程"。


class AkShareAdapter(StockDataSourceAdapter):
    """
    AKShare 数据源适配器。

    职责：把 AKShare 的原始数据翻译成系统统一格式。

    使用方式（你不直接调用，由框架调用）：
      1. fetch_stock_list()    → 从 AKShare 拉取原始股票列表
      2. normalize_stock_list() → 把原始数据转成 NormalizedStock 列表
      3. fetch_daily_bars()    → 从 AKShare 拉取原始日K线数据
      4. normalize_daily_bars() → 把原始数据转成 NormalizedDailyBar 列表
    """

    # ===== 类级别属性（元信息，框架用来识别和排序适配器） =====

    code = "akshare"  # 适配器的唯一标识符
    name = "AKShare"  # 人类可读的名称
    priority = 10  # 优先级（数字越小越优先，10 表示较高优先级）
    requires_token = False  # 不需要 API Token（免费数据源）
    default_enabled = True  # 默认启用

    # ===== 生命周期 =====

    def __init__(self, *, client: Any | None = None) -> None:
        """
        初始化适配器。

        参数 client 是为测试预留的：测试时可以传入 mock 对象，
        避免真的去调 AKShare。生产环境不传，让 _get_client() 自动加载。
        """
        self._client = client  # 以 _ 开头 = 私有属性，外面不要直接访问

    # ===== 能力宣告 =====

    def capabilities(self) -> AdapterCapability:
        """
        告诉框架：这个适配器能做什么？

        AKShare 适配器能提供：
          - 股票列表 ✓
          - 日K线  ✓（支持上交所、深交所、北交所）
          - 交易日历 ✗（不支持）
        """
        return AdapterCapability(
            stock_list=True,
            daily_bars=True,
            daily_bar_exchanges=("SSE", "SZSE", "BSE"),
        )

    def metadata(self) -> ProviderMetadata:
        """
        返回数据源的元信息（给用户看的说明）。

        包括：是什么类型、官网在哪、文档在哪、怎么认证、
        是否稳定、有没有频率限制、怎么安装。
        """
        return ProviderMetadata(
            provider_type="python_package",  # 是 Python 包，不是外部 API
            homepage_url="https://github.com/akfamily/akshare",
            docs_url="https://akshare.akfamily.xyz/data/stock/stock.html",
            auth_mode="none",  # 无需认证（免费）
            stability="community",  # 社区维护，非商业级稳定性
            rate_limit_note="Depends on upstream public data functions exposed by AKShare.",
            install_note="Install optional package: pip install akshare.",
        )

    # ===== 健康检查 =====

    def health_check(self) -> HealthCheckResult:
        """
        检查 AKShare 包是否安装、是否能正常工作。

        三种可能的结果：
          ① "healthy"     — 包已安装，且找到了需要的函数
          ② "unavailable" — 包没装（pip install akshare 即可）
          ③ "unhealthy"   — 包装了但有问题（比如版本太旧，缺少需要的函数）

        这个检查不拉数据，只看函数是否存在 —— hasattr 是 Python 内置函数，
        用来检查对象有没有某个属性/方法，速度很快。
        """
        try:
            client = self._get_client()

            # 检查有没有股票列表函数（至少有一个就行）
            stock_list_available = hasattr(client, "stock_info_a_code_name") or hasattr(client, "stock_zh_a_spot_em")
            # 检查有没有日K线函数（至少有一个就行）
            daily_bars_available = hasattr(client, "stock_zh_a_hist") or hasattr(client, "stock_zh_a_daily")

            if not stock_list_available and not daily_bars_available:
                return HealthCheckResult(
                    healthy=False,
                    status="unhealthy",
                    message="AKShare is installed, but supported A-share stock-list"
                    " or daily-bars functions were not found.",
                )
        except ModuleNotFoundError as exc:
            # 最外层没装 akshare 包
            logger.warning("AKShare not installed: %s", exc)
            return HealthCheckResult(
                healthy=False,
                status="unavailable",
                message=str(exc),
            )
        except Exception as exc:
            # 其他未知错误（网络问题、版本不兼容等）
            logger.warning("AKShare health check failed: %s", exc)
            return HealthCheckResult(healthy=False, status="unhealthy", message=str(exc))

        # 一切正常
        return HealthCheckResult(healthy=True, status="healthy", message="AKShare package is available.")

    # ===== 获取股票列表 =====

    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        从 AKShare 获取 A 股全部股票列表。

        流程：
          1. 检查 market 是不是 "A_SHARE"（目前只支持 A 股）
          2. 找到可用的 AKShare 函数（准备多个备选方案）
          3. 用 _try_fetch 逐个尝试，直到有一个成功

        返回值示例：
          [{"代码": "000001", "名称": "平安银行", "上市日期": "19910403"},
           {"代码": "000002", "名称": "万科A",   "上市日期": "19910129"},
           ...]  ← 4000+ 只 A 股

        注意：这时候的数据还是 AKShare 的原始格式（中文键名），
        后面要经过 normalize_stock_list() 才会变成系统统一格式。
        """
        if market.upper() != "A_SHARE":
            raise ValueError("AKShare stock list adapter currently supports A_SHARE only.")

        client = self._get_client()

        # 准备备选方案列表：哪个函数可用就用哪个
        candidates: list[tuple[str, Any]] = []

        # 方案一（较新的 AKShare 版本，最快）
        if hasattr(client, "stock_info_a_code_name"):
            candidates.append(
                (
                    "stock_info_a_code_name",
                    lambda: _records_from_frame(client.stock_info_a_code_name()),
                )
            )

        # 方案二（带实时行情字段，较慢）
        if hasattr(client, "stock_zh_a_spot_em"):
            candidates.append(
                (
                    "stock_zh_a_spot_em",
                    lambda: _records_from_frame(client.stock_zh_a_spot_em()),
                )
            )

        if not candidates:
            raise RuntimeError("AKShare client does not expose a supported A-share stock-list function.")

        try:
            return _try_fetch(candidates)
        except RuntimeError as exc:
            # 包装一下错误信息，让调用方知道是 AKShare 股票列表获取失败
            logger.warning("AKShare stock-list fetch failed: %s", exc)
            raise RuntimeError(f"AKShare stock-list fetch failed: {exc}") from exc

    def normalize_stock_list(self, raw_records: list[dict[str, Any]]) -> list[NormalizedStock]:
        """
        把 AKShare 的原始股票数据翻译成系统统一格式（NormalizedStock）。

        这就是适配器的核心工作：数据格式转换。

        输入（AKShare 原始数据）：
          {"代码": "000001", "名称": "平安银行", "上市日期": "19910403"}

        输出（系统统一格式）：
          NormalizedStock(
              symbol="000001",
              exchange="SZSE",
              market="A_SHARE",
              name="平安银行",
              status="LISTED",
              listing_date=date(1991, 4, 3),
              ...
          )

        为什么要统一格式？
          不同数据源叫法不同：有的叫"代码"，有的叫"code"，有的叫"证券代码"
          统一为 NormalizedStock 后，系统其他部分就不需要关心数据来源了。
        """
        normalized: list[NormalizedStock] = []

        for record in raw_records:
            # ---- 步骤 1：提取关键字段（兼容多种命名风格） ----
            # 用 or 链尝试多个可能的字段名，谁有值用谁
            symbol = _clean_text(
                record.get("code")  # TX：英文名
                or record.get("代码")  # 中文名
                or record.get("证券代码")  # 另一种中文名
            )
            name = _clean_text(record.get("name") or record.get("名称") or record.get("证券简称"))

            # 行业字段：stock_info_a_code_name 无此字段，stock_zh_a_spot_em 也无
            # 行业数据可从同花顺板块数据（POST /api/market/sectors/sync）补全
            industry = None

            # 没有代码或名称的记录直接跳过（可能是脏数据）
            if symbol is None or name is None:
                continue

            # ---- 步骤 2：构建标准化的 NormalizedStock 对象 ----
            normalized.append(
                NormalizedStock(
                    symbol=symbol,
                    exchange=_infer_exchange(symbol),  # 靠代码前缀推断交易所
                    market="A_SHARE",  # AKShare 目前只支持 A 股
                    name=name,
                    status="LISTED",  # 默认"上市中"
                    industry=industry,
                    listing_date=self._parse_listing_date(record),
                    delisting_date=None,  # AKShare 不提供退市日期
                    source=self.code,  # 标记数据来源 = "akshare"
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
        从 AKShare 获取某只股票的历史日K线数据。

        参数说明：
          symbol     — 股票代码，如 "600519"（贵州茅台）
          exchange   — 交易所，如 "SSE"。有些函数需要这个来构建新浪格式的代码
          market     — 市场类型，目前只支持 "A_SHARE"
          start_date — 开始日期
          end_date   — 结束日期

        流程和 fetch_stock_list 类似：
          准备多个备选函数 → _try_fetch 依次尝试

        关于日K线（OHLC）：
          日K线包含四个核心价格：开盘价(Open)、最高价(High)、最低价(Low)、收盘价(Close)
          简称 OHLC，是量化分析最基本的数据单元。
        """
        if market.upper() != "A_SHARE":
            raise ValueError("AKShare daily bars adapter currently supports A_SHARE only.")
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        adjust = "" if adjust_type_code == "none" else adjust_type_code

        client = self._get_client()

        # AKShare 要求日期格式为 "20240102"（无分隔符）
        start_text = start_date.strftime("%Y%m%d")
        end_text = end_date.strftime("%Y%m%d")

        candidates: list[tuple[str, Any]] = []

        # ---- 方案一：stock_zh_a_hist（推荐，较新版本的 AKShare） ----
        if hasattr(client, "stock_zh_a_hist"):
            hist_func = client.stock_zh_a_hist

            # 准备参数
            hist_kwargs: dict[str, Any] = {
                "symbol": symbol,
                "period": "daily",  # 日线数据（不是周线或月线）
                "start_date": start_text,
                "end_date": end_text,
                "adjust": adjust,
            }

            # 如果这个版本的 AKShare 支持 timeout 参数，就加上（防网络超时）
            if _supports_parameter(hist_func, "timeout"):
                hist_kwargs["timeout"] = 15  # 15 秒超时

            candidates.append(
                (
                    "stock_zh_a_hist",
                    lambda: _records_from_frame(hist_func(**hist_kwargs)),
                )
            )

        # ---- 方案二：stock_zh_a_daily（备选，旧版/不同接口） ----
        # 这个函数需要新浪格式的代码（如 "sh600519"），所以要转换
        if hasattr(client, "stock_zh_a_daily"):
            candidates.append(
                (
                    "stock_zh_a_daily",
                    lambda: _records_with_symbol(
                        client.stock_zh_a_daily(
                            symbol=_to_sina_symbol(symbol, exchange),
                            start_date=start_text,
                            end_date=end_text,
                            adjust=adjust,
                        ),
                        symbol,  # 补上 symbol，因为这个函数返回的数据里可能没有
                    ),
                )
            )

        if not candidates:
            raise RuntimeError("AKShare client does not expose a supported A-share daily-bars function.")

        try:
            return [{**record, "__adjust_type": adjust_type_code} for record in _try_fetch(candidates)]
        except RuntimeError as exc:
            raise RuntimeError(f"AKShare daily-bars fetch failed: {exc}") from exc

    def normalize_daily_bars(self, raw_records: list[dict[str, Any]]) -> list[NormalizedDailyBar]:
        """
        把 AKShare 的原始日K线数据翻译成系统统一格式（NormalizedDailyBar）。

        输入（AKShare 原始数据）：
          {"日期": "2024-01-02", "开盘": 10.0, "收盘": 10.5,
           "最高": 10.8, "最低": 9.9, "成交量": 12345678, "成交额": 130000000}

        输出（系统统一格式）：
          NormalizedDailyBar(
              symbol="600519", trade_date=date(2024,1,2),
              open=10.0, high=10.8, low=9.9, close=10.5,
              volume=12345678.0, amount=130000000.0, ...
          )

        和 normalize_stock_list 一样，兼容中文和英文两种字段名。
        """
        normalized: list[NormalizedDailyBar] = []

        for record in raw_records:
            # ---- 步骤 1：提取关键字段 ----
            symbol = _clean_text(
                record.get("股票代码")  # AKShare 某些函数用的中文名
                or record.get("symbol")  # 英文名（可能是我们之前补上的）
                or record.get("code")  # 另一种英文名
            )
            trade_date = _parse_date(record.get("日期") or record.get("date") or record.get("trade_date"))

            if symbol is None or trade_date is None:
                continue  # 缺少关键字段，跳过

            # ---- 步骤 2：提取 OHLC 价格 ----
            open_price = _to_float(record.get("开盘") or record.get("open"))
            high = _to_float(record.get("最高") or record.get("high"))
            low = _to_float(record.get("最低") or record.get("low"))
            close = _to_float(record.get("收盘") or record.get("close"))

            # 四个价格缺一不可（缺了就没法做技术分析）
            if open_price is None or high is None or low is None or close is None:
                continue

            # ---- 步骤 3：提取成交量和成交额（这两个可选） ----
            # default=0.0 表示取不到就用 0
            volume = (
                _to_float(
                    record.get("成交量") or record.get("volume"),
                    default=0.0,
                )
                or 0.0
            )
            amount = (
                _to_float(
                    record.get("成交额") or record.get("amount"),
                    default=0.0,
                )
                or 0.0
            )

            # ---- 步骤 4：构建标准化对象 ----
            normalized.append(
                NormalizedDailyBar(
                    symbol=symbol,
                    exchange=_infer_exchange(symbol),
                    market="A_SHARE",
                    trade_date=trade_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    pre_close=None,  # AKShare 不提供前收盘价
                    volume=volume,
                    amount=amount,
                    adjust_factor=1.0,  # 不复权数据，因子固定为 1
                    adjust_type=normalize_daily_bar_adjust_type(
                        record.get("__adjust_type") or record.get("adjust_type")
                    ),
                    source=self.code,
                )
            )

        return normalized

    # ===== 内部辅助 =====

    def _get_client(self) -> Any:
        """
        懒加载（Lazy Loading）AKShare 模块。

        所谓"懒加载"就是：不用的时候不加载，第一次用到时才加载。
        这样做的好处：
          ① 启动快 — 不会因为装了一个不用的数据源就拖慢启动
          ② 容错 — 如果 akshare 没装，只有真正调用数据时才会报错

        import_module("akshare") 等价于 import akshare，
        但返回的是模块对象，可以动态调用。
        """
        if self._client is None:
            self._client = import_module("akshare")
        return self._client

    @staticmethod
    def _parse_listing_date(record: dict[str, Any]) -> date | None:
        """
        从原始记录中提取上市日期。

        @staticmethod 表示这是一个静态方法——不需要访问 self，
        只是逻辑上属于这个类，放在类里比放在外面更清晰。
        """
        raw_value = _clean_text(record.get("上市日期") or record.get("listing_date"))
        if raw_value is None:
            return None
        return _parse_date(raw_value)


# =============================================================================
# 第三部分：全局数据解析函数
# =============================================================================
# 这两个函数放在类外面，因为它俩足够通用 —— 不限于 AKShare，
# 其他适配器也可能需要解析日期和浮点数。


def _parse_date(value: Any) -> date | None:
    """
    把各种可能格式的日期值统一解析为 Python date 对象。

    AKShare 不同函数返回的日期格式不一样：
      - 有时是字符串 "2024-01-02"
      - 有时是字符串 "20240102"（无分隔符）
      - 有时是字符串 "2024/01/02"（斜杠分隔）
      - 有时已经是 date 对象了

    这个函数把这些情况都兜住，返回统一的 date 对象。

    示例：
      _parse_date("2024-01-02")    → date(2024, 1, 2)
      _parse_date("20240102")      → date(2024, 1, 2)
      _parse_date("2024/01/02")    → date(2024, 1, 2)
      _parse_date(date(2024,1,2))  → date(2024, 1, 2)  （已经是了，直接返回）
      _parse_date(None)            → None
    """
    if isinstance(value, date):
        return value  # 已经是 date 对象，不用转了

    text = _clean_text(value)
    if text is None:
        return None

    # 去掉所有分隔符，得到纯数字字符串
    # 如 "2024-01-02" → "20240102"
    digits = text.replace("-", "").replace("/", "")

    # 8 位纯数字 → 用切片取年、月、日
    if len(digits) == 8 and digits.isdigit():
        return date(
            int(digits[:4]),  # 前 4 位 = 年份
            int(digits[4:6]),  # 中间 2 位 = 月份
            int(digits[6:8]),  # 最后 2 位 = 日期
        )

    # 其他格式（如 "2024-01-02"）交给 Python 标准库解析
    return date.fromisoformat(text.replace("/", "-"))


def _to_float(value: Any, *, default: float | None = None) -> float | None:
    """
    安全地把一个值转为 float（浮点数）。

    在量化分析中，价格、成交量等都必须是数字才能计算。
    但原始数据里可能是字符串 "10.5" 或空值 ""，需要统一转换。

    示例：
      _to_float("10.5")          → 10.5
      _to_float(10)              → 10.0
      _to_float(None)            → None
      _to_float(None, default=0) → 0.0   （指定了默认值）
    """
    text = _clean_text(value)
    if text is None:
        return default
    return float(text)
