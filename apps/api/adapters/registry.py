from __future__ import annotations

from apps.api.adapters.adata import ADataAdapter
from apps.api.adapters.akshare import AkShareAdapter
from apps.api.adapters.baostock import BaoStockAdapter
from apps.api.adapters.base import StockDataSourceAdapter
from apps.api.adapters.stock_sdk import StockSdkAdapter
from apps.api.adapters.tushare import TushareAdapter


# =============================================================================
# 【小白必读】registry.py 是什么？
# =============================================================================
#
# Registry = 注册中心。你可以把它想象成手机里的"联系人列表"：
#   - 你有 5 个朋友（AKShare、BaoStock、AData、Tushare、StockSDK）
#   - 每个人的手机号可能不同，但你存了"名字 → 手机号"的映射
#   - 你想找谁，报他的名字就行，不用记号码
#
# AdapterRegistry 就是这个联系人列表：
#   名字（code）= "akshare" / "baostock" / ...
#   手机号（adapter）= AkShareAdapter / BaoStockAdapter / ...
#
# 为什么需要一个注册中心？
#   ① 统一管理 — 所有适配器在一个地方登记，谁在哪一目了然
#   ② 按需查找 — 系统可以说"给我一个能做日K线的适配器"，注册中心帮你找
#   ③ 解耦 — 上层代码只依赖 AdapterRegistry，不直接依赖某个具体的适配器


class AdapterRegistry:
    """
    适配器注册中心 —— 管理所有数据源适配器。

    设计模式：注册表模式（Registry Pattern）
      把所有同类型的对象集中管理，通过 key 来查找。

    使用示例：
      registry = AdapterRegistry()
      registry.register(AkShareAdapter())          # 登记 AKShare
      registry.register(BaoStockAdapter())         # 登记 BaoStock

      adapter = registry.get("akshare")            # 按名字取适配器
      adapter.fetch_stock_list(market="A_SHARE")   # 用它拉数据

    关键设计：
      - 用 dict 存储适配器，code 作为 key，查找是 O(1) 的
      - priority 决定排序 —— 数字越小越靠前
      - 可以按能力筛选（"谁能做日K线？"）
    """

    def __init__(self) -> None:
        """
        初始化注册中心。

        _adapters 是一个字典：
          {"akshare": AkShareAdapter(), "baostock": BaoStockAdapter(), ...}

        前缀 _ 表示私有属性 —— 外面的代码不要直接访问这个字典，
        而是通过 get() / list() 方法来获取适配器。
        这样做的好处是：
          如果以后想把 dict 换成别的数据结构（如 Redis），
          只需要改这个类的内部实现，调用方不受影响。
          这叫做"封装变化"。
        """
        self._adapters: dict[str, StockDataSourceAdapter] = {}

    def register(self, adapter: StockDataSourceAdapter) -> None:
        """
        登记一个适配器。

        参数 adapter 必须是 StockDataSourceAdapter 的子类实例。
        adapter.code 是它在注册中心里的唯一标识符（如 "akshare"）。

        注意：相同 code 的适配器，后注册的会覆盖先注册的。
        这是设计上的选择 —— 允许外部用自定义适配器替换默认的。
        """
        self._adapters[adapter.code] = adapter

    def get(self, code: str) -> StockDataSourceAdapter:
        """
        按 code 获取指定的适配器。

        如果 code 不存在，会抛 ValueError 并列出所有可用的适配器名字。
        这是一个友好的错误信息，帮助用户快速定位问题：
          "Unknown data source 'wind'. Available sources: adata, akshare, baostock, ..."
        """
        try:
            return self._adapters[code]
        except KeyError as exc:
            # 列出所有可用的名字，帮助用户知道正确的 code 是什么
            available = ", ".join(sorted(self._adapters))
            raise ValueError(
                f"Unknown data source '{code}'. Available sources: {available}"
            ) from exc

    def list(self) -> list[StockDataSourceAdapter]:
        """
        返回所有已注册的适配器，按优先级排序（priority 小的在前）。

        排序的意义：
          框架想尝试拉数据时，优先用高优先级的适配器。
          比如：先试 AKShare（免费，priority=10），
               不行再试 BaoStock（免费，priority=20），
               还不行试 Tushare（需要 Token，priority=30）。

        这叫做"fallback chain"（自动降级链）：
        用户不需要手动选数据源，系统自动按优先级切换。
        """
        return sorted(
            self._adapters.values(),
            key=lambda adapter: adapter.priority,
        )

    def list_for_capability(self, capability: str) -> list[StockDataSourceAdapter]:
        """
        按能力筛选适配器。只看那些"能做 X"的适配器。

        参数 capability 是能力名（如 "stock_list"、"daily_bars"、"calendars"）。

        实现原理：
          对每个适配器，调用它的 capabilities() 方法获取能力清单，
          然后用 getattr() 取出对应字段，检查是否为 True。

        示例：
          registry.list_for_capability("daily_bars")
          → [AkShareAdapter, BaoStockAdapter, ADataAdapter, TushareAdapter, StockSdkAdapter]
             （所有支持日K线的适配器）

          registry.list_for_capability("calendars")
          → [BaoStockAdapter, TushareAdapter]
             （只有这两个支持交易日历）
        """
        return [
            adapter
            for adapter in self.list()
            # getattr(obj, attr_name, default) —— 反射机制
            # 比如 getattr(adapter.capabilities(), "daily_bars", False)
            # → 取 adapter.capabilities().daily_bars，取不到就返回 False
            if bool(getattr(adapter.capabilities(), capability, False))
        ]


def default_adapter_registry() -> AdapterRegistry:
    """
    创建默认的适配器注册中心，包含所有内置适配器。

    这就是系统的"默认配置"——启动时调用一次，把所有能用的数据源登记上。

    当前内置的 5 个适配器：
      序号 | code       | name       | priority | 需要 Token | 特点
      ─────┼────────────┼────────────┼──────────┼────────────┼──────────────
      1    | akshare    | AKShare    | 10       | 否          | 免费优先，纯 Python
      2    | baostock   | BaoStock   | 20       | 否          | 免费，数据全（含日历）
      3    | adata      | AData      | 25       | 否          | 免费，纯 Python
      4    | tushare    | Tushare    | 30       | 是          | 需要注册获取 Token
      5    | stock_sdk  | Stock SDK  | 45       | 否          | Node.js 包，实验性

    优先级的设计逻辑：
      - 免费的排前面（用户不需要额外配置就能用）
      - 功能完整的排在前面（能提供更多数据类型）
      - 需要配置的排后面（有门槛，不是开箱即用）

    如何新增一个数据源？
      1. 写一个继承 StockDataSourceAdapter 的子类
      2. 在这里注册它：registry.register(YourNewAdapter())
      3. 完成！系统其他部分不需要改动。
    """
    registry = AdapterRegistry()
    registry.register(AkShareAdapter())
    registry.register(BaoStockAdapter())
    registry.register(ADataAdapter())
    registry.register(TushareAdapter())
    registry.register(StockSdkAdapter())
    return registry
