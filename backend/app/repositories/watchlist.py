"""自选股仓储。ponytail: 不搞复杂查询，只 5 个动作——确保默认分组 + 列表 + 添加 + 删除 + 重排。

name='default' 是固定小组，所有用户的自选股都进这里；以后做多用户/多群组只要扩 group 逻辑即可。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import Watchlist, WatchlistItem


DEFAULT_WATCHLIST_NAME = "default"


def get_or_create_default_watchlist(db: Session) -> Watchlist:
    wl = db.scalar(select(Watchlist).where(Watchlist.name == DEFAULT_WATCHLIST_NAME))
    if wl is None:
        wl = Watchlist(name=DEFAULT_WATCHLIST_NAME)
        db.add(wl)
        db.commit()
        db.refresh(wl)
    return wl


def list_items(db: Session, watchlist_id: int) -> list[WatchlistItem]:
    stmt = (
        select(WatchlistItem)
        .where(WatchlistItem.watchlist_id == watchlist_id)
        .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.added_at.asc())
    )
    return list(db.scalars(stmt).all())


def add_item(
    db: Session, watchlist_id: int, symbol: str, note: Optional[str] = None
) -> tuple[WatchlistItem, bool]:
    """返回 (item, created)。已存在时返回已有的 + created=False（不抛异常）"""
    symbol = symbol.strip().lower()
    existing = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol == symbol,
        )
    )
    if existing is not None:
        if note is not None:
            existing.note = note
        db.commit()
        db.refresh(existing)
        return existing, False

    max_order = db.scalar(
        select(func.coalesce(func.max(WatchlistItem.sort_order), 0)).where(
            WatchlistItem.watchlist_id == watchlist_id
        )
    ) or 0
    item = WatchlistItem(
        watchlist_id=watchlist_id,
        symbol=symbol,
        note=note,
        sort_order=int(max_order) + 10,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item, True


def remove_item(db: Session, watchlist_id: int, symbol: str) -> bool:
    symbol = symbol.strip().lower()
    item = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol == symbol,
        )
    )
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


def reorder_items(db: Session, watchlist_id: int, symbols: list[str]) -> int:
    """按传入 symbols 顺序写 sort_order，单调递增 10。返回被更新的条数。"""
    symbols = [s.strip().lower() for s in symbols]
    rows = db.scalars(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol.in_(symbols),
        )
    ).all()
    by_symbol = {r.symbol: r for r in rows}
    updated = 0
    for idx, sym in enumerate(symbols):
        r = by_symbol.get(sym)
        if r is not None:
            r.sort_order = (idx + 1) * 10
            updated += 1
    db.commit()
    return updated
