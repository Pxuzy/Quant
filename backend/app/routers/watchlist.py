"""自选股 API。ponytail: 5 个端点刚好够用——GET 列表 / POST 添加 / DELETE 删除 / PUT 重排 / 清空。

默认只有一个 'default' group；不做多用户/多群组/认证。后续扩展只需要换仓库层，路由不变。
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.repositories import watchlist as watchlist_repo
from backend.app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead, WatchlistRead

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemRead])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItemRead]:
    """获取默认分组的全部自选股，按 sort_order 升序。"""
    wl = watchlist_repo.get_or_create_default_watchlist(db)
    items = watchlist_repo.list_items(db, watchlist_id=wl.id)
    return [WatchlistItemRead.model_validate(i) for i in items]


@router.get("/group", response_model=WatchlistRead)
def get_default_group(db: Session = Depends(get_db)) -> WatchlistRead:
    """获取/创建默认 group 信息。"""
    wl = watchlist_repo.get_or_create_default_watchlist(db)
    return WatchlistRead.model_validate(wl)


@router.post("/items", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
def add_item(payload: WatchlistItemCreate, db: Session = Depends(get_db)) -> WatchlistItemRead:
    """添加自选股。已存在则更新 note 并返回 200（不重复添加也不抛错）。"""
    wl = watchlist_repo.get_or_create_default_watchlist(db)
    item, _created = watchlist_repo.add_item(
        db,
        watchlist_id=wl.id,
        symbol=payload.symbol,
        note=payload.note,
    )
    return WatchlistItemRead.model_validate(item)


@router.delete("/items/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(symbol: str, db: Session = Depends(get_db)) -> None:
    """按 symbol 删除自选股。股票编码大小写不敏感。"""
    wl = watchlist_repo.get_or_create_default_watchlist(db)
    ok = watchlist_repo.remove_item(db, watchlist_id=wl.id, symbol=symbol)
    if not ok:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")


@router.put("/items/reorder", response_model=dict)
def reorder(symbols: list[str] = Body(..., embed=True), db: Session = Depends(get_db)) -> dict:
    """重排：传入完整顺序（仅包含已添加的股票）。"""
    wl = watchlist_repo.get_or_create_default_watchlist(db)
    updated = watchlist_repo.reorder_items(db, watchlist_id=wl.id, symbols=symbols)
    return {"updated": updated}
