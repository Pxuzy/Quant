# =============================================================================
# 【小白必读】__init__.py 是什么？
# =============================================================================
#
# 在 Python 中，一个目录里有 __init__.py 就表示这个目录是一个包（package）。
# 别的地方可以写：from apps.api.adapters import ...
#
# 这个文件做了两件事：
#
#   ① 导入（import）—— 把常用类从子模块"提升"到包级别
#      这样使用者不用写：
#        from apps.api.adapters.base import NormalizedStock
#      而可以写：
#        from apps.api.adapters import NormalizedStock
#      更简洁，也隐藏了内部目录结构。
#
#   ② __all__ —— 控制 "from apps.api.adapters import *" 时导出什么
#      这是一种"白名单"机制。如果不定义 __all__，
#      import * 会把所有公开名字都导出（包括内部函数），
#      可能污染使用者的命名空间。

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedStock,
    StockDataSourceAdapter,
)
from apps.api.adapters.registry import default_adapter_registry

# __all__ 定义了 from ... import * 时对外暴露的名字
# 这里只暴露最常用的 5 个：
#   - 3 个核心数据结构（NormalizedStock, AdapterCapability, HealthCheckResult）
#   - 1 个抽象基类（StockDataSourceAdapter）
#   - 1 个工厂函数（default_adapter_registry）
__all__ = [
    "AdapterCapability",
    "HealthCheckResult",
    "NormalizedStock",
    "StockDataSourceAdapter",
    "default_adapter_registry",
]
