from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from apps.api.models.entities import NewsArticle


class NewsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_many(self, records: list[dict]) -> int:
        """批量写入新闻，按 (source, external_id) 去重"""
        written = 0
        for record in records:
            external_id = record.get("external_id") or record.get("url", "")
            source = record.get("source", "sina")

            existing = self.db.scalar(
                select(NewsArticle).where(
                    NewsArticle.source == source,
                    NewsArticle.external_id == external_id,
                )
            )

            if existing is None:
                article = NewsArticle(
                    title=record["title"],
                    url=record.get("url"),
                    summary=record.get("summary"),
                    source=source,
                    category=record.get("category"),
                    related_symbols=record.get("related_symbols", []),
                    external_id=external_id,
                    published_at=record.get("published_at"),
                )
                self.db.add(article)
                written += 1
            else:
                # Update existing record
                existing.title = record["title"]
                existing.summary = record.get("summary")
                existing.category = record.get("category")
                existing.related_symbols = record.get("related_symbols", [])
                written += 1
        self.db.flush()
        return written

    def list_news(
        self,
        *,
        keyword: str | None = None,
        source: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[NewsArticle], int]:
        conditions = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    NewsArticle.title.ilike(pattern),
                    NewsArticle.summary.ilike(pattern),
                )
            )
        if source:
            conditions.append(NewsArticle.source == source.strip())
        if category:
            conditions.append(NewsArticle.category == category.strip())

        total_stmt = select(func.count(NewsArticle.id))
        records_stmt = select(NewsArticle).order_by(
            desc(NewsArticle.published_at), desc(NewsArticle.created_at)
        )
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        records = self.db.scalars(
            records_stmt.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(records), total

    def count(self) -> int:
        return self.db.scalar(select(func.count(NewsArticle.id))) or 0

    def latest_published_at(self) -> datetime | None:
        return self.db.scalar(
            select(func.max(NewsArticle.published_at))
        )

    def delete_old(self, *, keep_days: int = 30) -> int:
        """删除超过 keep_days 天的新闻"""
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=keep_days)

        result = self.db.execute(
            # SQLAlchemy 2.0 style
            select(NewsArticle).where(NewsArticle.created_at < cutoff)
        )
        old_articles = result.scalars().all()
        count = len(old_articles)
        for article in old_articles:
            self.db.delete(article)
        self.db.flush()
        return count
