"""数据层查询缓存管理。

后端 service/repository 层通过此模块失效 data_loader 的查询缓存，
避免 backend → scripts 的逆向依赖。

模块级单例 `_DATA_LOADER_REF` 由首次调用时懒加载。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.data_loader import DataAccessLayer


_DATA_LOADER_REF: DataAccessLayer | None = None


def _get_data_loader():
    global _DATA_LOADER_REF
    if _DATA_LOADER_REF is None:
        from scripts.data_loader import _get_dal

        _DATA_LOADER_REF = _get_dal()
    return _DATA_LOADER_REF


def invalidate_data_cache(cache_name: str | None = None) -> None:
    """失效 data_loader 的查询缓存（stocks/calendar/search）。

    cache_name=None 时失效全部缓存。
    """
    dal = _get_data_loader()
    dal.invalidate_cache(cache_name)
