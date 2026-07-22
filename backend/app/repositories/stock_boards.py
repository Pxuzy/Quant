from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models import StockBoard, StockBoardMember
from backend.app.repositories._base import BaseRepository


class StockBoardRepository(BaseRepository):

    def list_boards(self, *, category: str | None = None) -> list[StockBoard]:
        stmt = select(StockBoard).order_by(StockBoard.category, StockBoard.change_pct.desc().nullslast(), StockBoard.name)
        if category:
            stmt = stmt.where(StockBoard.category == category.strip())
        return list(self.db.scalars(stmt).all())

    def get_board(self, *, name: str, category: str | None = None) -> StockBoard | None:
        stmt = select(StockBoard).where(StockBoard.name == name.strip())
        if category:
            stmt = stmt.where(StockBoard.category == category.strip())
        return self.db.scalar(stmt.order_by(StockBoard.category).limit(1))

    def upsert_boards(self, records: list[dict]) -> int:
        written = 0
        for record in records:
            name = str(record["name"]).strip()
            category = str(record["category"]).strip()
            board = self.db.scalar(
                select(StockBoard).where(
                    StockBoard.name == name,
                    StockBoard.category == category,
                )
            )
            if board is None:
                board = StockBoard(
                    name=name,
                    category=category,
                    source=str(record.get("source") or "unknown"),
                )
                self.db.add(board)

            board.source = str(record.get("source") or board.source)
            board.provider_code = _text_or_none(record.get("provider_code"))
            board.change_pct = _float_or_none(record.get("change_pct"))
            board.up_count = int(record.get("up_count") or 0)
            board.down_count = int(record.get("down_count") or 0)
            board.stock_count = int(record.get("stock_count") or 0)
            board.amount = float(record.get("amount") or 0)
            board.volume = float(record.get("volume") or 0)
            board.net_inflow = _float_or_none(record.get("net_inflow"))
            board.leader_name = _text_or_none(record.get("leader_name"))
            board.leader_price = _float_or_none(record.get("leader_price"))
            board.leader_change_pct = _float_or_none(record.get("leader_change_pct"))
            written += 1
        self.db.flush()
        return written

    def replace_members(self, *, board: StockBoard, members: list[dict], source: str) -> int:
        self.db.execute(delete(StockBoardMember).where(StockBoardMember.board_id == board.id))
        for member in members:
            self.db.add(
                StockBoardMember(
                    board_id=board.id,
                    symbol=str(member["symbol"]).strip(),
                    exchange=str(member["exchange"]).strip().upper(),
                    name=str(member["name"]).strip(),
                    source=source,
                )
            )
        self.db.flush()
        return len(members)

    def list_members(self, *, board: StockBoard) -> list[StockBoardMember]:
        return list(
            self.db.scalars(
                select(StockBoardMember)
                .where(StockBoardMember.board_id == board.id)
                .order_by(StockBoardMember.exchange, StockBoardMember.symbol)
            ).all()
        )


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
