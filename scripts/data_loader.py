"""
DataLoader — Qlib 式 DataBundle，双引擎版。

统一的数据查询入口。业务代码只调这 8 个函数，不感知底层有几个库。

路由规则：
  stocks / search / calendar / news     → PG/SQLite (SQLAlchemy)
  daily_bars / fundamentals / factors   → DuckDB 持久表
  search_knowledge                      → PG+pgvector (cosine)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from cachetools import TTLCache
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


# ─── DataAccessLayer ─────────────────────────────────────
# 三态引擎：PG / SQLite / DuckDB，按 database_url 自动选择。


@dataclass
class DataAccessLayer:
    """按 database_url 自动路由的统一数据访问层。"""

    database_url: str = ""
    duckdb_path: str = ""
    _engine: Any = field(default=None, repr=False)
    _session_factory: Any = field(default=None, repr=False)
    _duck: Any = field(default=None, repr=False)

    # 查询缓存：低频变化数据使用 TTL 缓存
    _cache: dict[str, TTLCache] = field(default_factory=lambda: {
        "stocks": TTLCache(maxsize=4, ttl=300),       # 5 分钟
        "calendar": TTLCache(maxsize=4, ttl=300),      # 5 分钟
        "search": TTLCache(maxsize=128, ttl=60),       # 1 分钟
    }, repr=False)

    def __post_init__(self) -> None:
        self.database_url = self.database_url or get_settings().database_url
        self.duckdb_path = self.duckdb_path or get_settings().duckdb_path

    # ── 引擎管理 ────────────────────────────────────────

    @property
    def is_pg(self) -> bool:
        return self.database_url.startswith("postgresql")

    def _get_engine(self):
        if self._engine is None:
            connect_args = {} if self.is_pg else {"check_same_thread": False}
            self._engine = create_engine(self.database_url, connect_args=connect_args, future=True)
            self._session_factory = sessionmaker(bind=self._engine)
        return self._engine

    def _get_session(self) -> Session:
        self._get_engine()
        return self._session_factory()

    def _get_duckdb(self):
        if self._duck is None:
            import duckdb as _duckdb

            db_path = Path(self.duckdb_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._duck = _duckdb.connect(str(db_path))
            self._init_duckdb_schema()
        return self._duck

    def _init_duckdb_schema(self) -> None:
        """Auto-create DuckDB tables if they don't exist."""
        import duckdb as _duckdb

        con = self._duck
        # daily_bars — mirrors the Parquet schema for unified access
        con.execute("""
            CREATE TABLE IF NOT EXISTS daily_bars (
                symbol          VARCHAR,
                exchange        VARCHAR,
                market          VARCHAR,
                trade_date      DATE,
                open            DOUBLE,
                high            DOUBLE,
                low             DOUBLE,
                close           DOUBLE,
                pre_close       DOUBLE,
                volume          DOUBLE,
                amount          DOUBLE,
                adjust_factor   DOUBLE,
                adjust_type     VARCHAR,
                source          VARCHAR,
                ingested_at     TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS factors_daily (
                symbol      VARCHAR,
                trade_date  DATE,
                factor_name VARCHAR,
                value       DOUBLE
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS financials_quarterly (
                symbol      VARCHAR,
                report_date DATE,
                metric_name VARCHAR,
                value       DOUBLE
            )
        """)

    def close(self) -> None:
        if self._duck is not None:
            self._duck.close()
            self._duck = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def invalidate_cache(self, cache_name: str | None = None) -> None:
        """清除查询缓存。cache_name 为 None 时清空全部。"""
        if cache_name and cache_name in self._cache:
            self._cache[cache_name].clear()
        elif cache_name is None:
            for c in self._cache.values():
                c.clear()

    # ── 对外接口 — 8 个函数 ─────────────────────────────

    def stocks(self, market: str = "A_SHARE") -> list[dict]:
        """全市场股票列表。返回 [{symbol, name, exchange, market, industry, listing_date, status}]"""
        cache_key = ("stocks", market)
        if cache_key in self._cache["stocks"]:
            return self._cache["stocks"][cache_key]
        session = self._get_session()
        try:
            rows = session.execute(
                text(
                    "SELECT symbol, name, exchange, market, industry, listing_date, status "
                    "FROM stocks WHERE market = :market ORDER BY symbol"
                ),
                {"market": market},
            ).fetchall()
            result = [dict(r._mapping) for r in rows]
            self._cache["stocks"][cache_key] = result
            return result
        finally:
            session.close()

    def search(self, keyword: str) -> list[dict]:
        """模糊搜股票。输入 '茅台' 或 '600519' 都行。"""
        cache_key = ("search", keyword.strip().lower())
        if cache_key in self._cache["search"]:
            return self._cache["search"][cache_key]
        session = self._get_session()
        try:
            like = f"%{keyword}%"
            if self.is_pg:
                stmt = text(
                    "SELECT symbol, name, exchange, market, industry FROM stocks "
                    "WHERE symbol ILIKE :kw OR name ILIKE :kw LIMIT 20"
                )
            else:
                stmt = text(
                    "SELECT symbol, name, exchange, market, industry FROM stocks "
                    "WHERE symbol LIKE :kw OR name LIKE :kw LIMIT 20"
                )
            rows = session.execute(stmt, {"kw": like}).fetchall()
            result = [dict(r._mapping) for r in rows]
            self._cache["search"][cache_key] = result
            return result
        finally:
            session.close()

    def calendar(self, market: str = "A_SHARE") -> dict[str, bool]:
        """交易日历。返回 {trade_date: is_open}"""
        cache_key = ("calendar", market)
        if cache_key in self._cache["calendar"]:
            return self._cache["calendar"][cache_key]
        session = self._get_session()
        try:
            rows = session.execute(
                text(
                    "SELECT trade_date, is_open FROM trading_calendars WHERE market = :market"
                ),
                {"market": market},
            ).fetchall()
            result = {str(r.trade_date): bool(r.is_open) for r in rows}
            self._cache["calendar"][cache_key] = result
            return result
        finally:
            session.close()

    def daily_bars(
        self,
        symbol: str,
        market: str = "A_SHARE",
        start: str | None = None,
        end: str | None = None,
        limit: int = 0,
    ) -> list[dict]:
        """单只股票 K 线。返回 [{trade_date, open, high, low, close, volume, amount}]"""
        con = self._get_duckdb()
        conditions = ["symbol = ?", "market = ?"]
        params: list[Any] = [symbol, market]
        if start:
            conditions.append("trade_date >= ?")
            params.append(start)
        if end:
            conditions.append("trade_date <= ?")
            params.append(end)

        sql = (
            "SELECT trade_date, open, high, low, close, volume, amount "
            "FROM daily_bars "
            "WHERE " + " AND ".join(conditions) +
            " ORDER BY trade_date"
        )

        if limit:
            sql += f" DESC LIMIT {limit}"
            rows = con.execute(sql, params).fetchall()
            rows.reverse()
        else:
            rows = con.execute(sql, params).fetchall()

        cols = ["trade_date", "open", "high", "low", "close", "volume", "amount"]
        return [dict(zip(cols, [str(r[0]) if hasattr(r[0], 'isoformat') else r[0], *r[1:]])) for r in rows]

    def fundamentals(
        self,
        symbol: str,
        year: int | None = None,
    ) -> list[dict]:
        """财报数据。返回 [{report_date, metric_name, value}]"""
        con = self._get_duckdb()
        conditions = ["symbol = ?"]
        params: list[Any] = [symbol]
        if year:
            conditions.append("EXTRACT(year FROM report_date) = ?")
            params.append(year)

        rows = con.execute(
            "SELECT report_date, metric_name, value FROM financials_quarterly "
            "WHERE " + " AND ".join(conditions) + " ORDER BY report_date",
            params,
        ).fetchall()
        return [dict(zip(["report_date", "metric_name", "value"], r)) for r in rows]

    def factors(
        self,
        symbol: str,
        factor_names: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """日频因子值。返回 [{trade_date, factor_name, value}]"""
        con = self._get_duckdb()
        conditions = ["symbol = ?"]
        params: list[Any] = [symbol]
        if factor_names:
            placeholders = ", ".join(["?" for _ in factor_names])
            conditions.append(f"factor_name IN ({placeholders})")
            params.extend(factor_names)
        if start:
            conditions.append("trade_date >= ?")
            params.append(start)
        if end:
            conditions.append("trade_date <= ?")
            params.append(end)

        rows = con.execute(
            "SELECT trade_date, factor_name, value FROM factors_daily "
            "WHERE " + " AND ".join(conditions) + " ORDER BY trade_date",
            params,
        ).fetchall()
        return [dict(zip(["trade_date", "factor_name", "value"], r)) for r in rows]

    def news(
        self,
        keyword: str | None = None,
        source: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """新闻查询。返回 (records, total)"""
        from backend.app.repositories.news_articles import NewsArticle, NewsRepository

        session = self._get_session()
        try:
            repo = NewsRepository(session)
            articles, total = repo.list_news(keyword=keyword, source=source, category=category, page=page, page_size=page_size)
            records = [
                {
                    "id": a.id,
                    "title": a.title,
                    "url": a.url,
                    "summary": a.summary,
                    "source": a.source,
                    "category": a.category,
                    "related_symbols": a.related_symbols,
                    "published_at": str(a.published_at) if a.published_at else None,
                    "created_at": str(a.created_at),
                }
                for a in articles
            ]
            return records, total
        finally:
            session.close()

    def search_knowledge(
        self,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict]:
        """语义搜索知识库（PG+pgvector 余弦相似度）。

        返回 [{id, title, content, similarity}]。
        SQLite 模式下降级为关键词搜索 news_articles。
        """
        if not self.is_pg:
            # SQLite 降级：搜索 news_articles 标题/摘要
            session = self._get_session()
            try:
                from backend.app.repositories.news_articles import NewsArticle

                articles, _ = NewsRepository(session).list_news(keyword="", page=1, page_size=limit)
                return [
                    {
                        "id": a.id,
                        "title": a.title,
                        "summary": a.summary,
                        "source": a.source,
                        "category": a.category,
                    }
                    for a in articles
                ]
            finally:
                session.close()

        # PG 模式：pgvector cosine search on news_articles
        session = self._get_session()
        try:
            embedding_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"
            rows = session.execute(
                text(f"""
                    SELECT id, title, summary, source, category,
                           1 - (embedding <=> '{embedding_literal}'::vector) AS similarity
                    FROM news_articles
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> '{embedding_literal}'::vector
                    LIMIT :lim
                """),
                {"lim": limit},
            ).fetchall()
            return [dict(r._mapping) for r in rows]
        finally:
            session.close()

    # ─── 便捷入口 ──────────────────────────────────────────

    def stock_detail(self, symbol: str, market: str = "A_SHARE") -> dict | None:
        """一只股票的全部信息：基础信息 + K 线 + 新鲜度。"""
        stocks_list = self.stocks(market=market)
        info = next((s for s in stocks_list if s["symbol"] == symbol), None)
        if not info:
            return None

        bars = self.daily_bars(symbol, market, limit=120)
        info["bars"] = bars
        info["latest_data_date"] = bars[-1]["trade_date"] if bars else None
        return info


# ─── 模块级单例 + 兼容旧接口 ──────────────────────────

_dal: DataAccessLayer | None = None


# ─── 缓存失效 ───────────────────────────────────────────

# 全局模块级 data_loader 缓存引用，由 _get_dal() 初始化
# 外部 sync service 通过 invalidate_data_cache() 在数据写入后失效
_DATA_CACHE_REF: DataAccessLayer | None = None


def invalidate_data_cache(cache_name: str | None = None) -> None:
    """失效 data_loader 的查询缓存（stocks/calendar/search）。

    由 sync service 在数据写入后调用。
    cache_name=None 时失效全部缓存。
    """
    global _DATA_CACHE_REF
    if _DATA_CACHE_REF is None:
        _DATA_CACHE_REF = _get_dal()
    _DATA_CACHE_REF.invalidate_cache(cache_name)


def _get_dal() -> DataAccessLayer:
    global _dal
    if _dal is None:
        _dal = DataAccessLayer()
    return _dal


# 保持与旧版相同的 6 个函数签名 ── 已有调用不受影响
def stocks(market: str = "A_SHARE") -> list[dict]:
    return _get_dal().stocks(market)


def search(keyword: str) -> list[dict]:
    return _get_dal().search(keyword)


def daily_bars(
    symbol: str,
    market: str = "A_SHARE",
    start: str | None = None,
    end: str | None = None,
    limit: int = 0,
) -> list[dict]:
    return _get_dal().daily_bars(symbol, market, start, end, limit)


def calendar(market: str = "A_SHARE") -> dict[str, bool]:
    return _get_dal().calendar(market)


def fundamentals(symbol: str, year: int | None = None) -> list[dict]:
    return _get_dal().fundamentals(symbol, year)


def stock_detail(symbol: str, market: str = "A_SHARE") -> dict | None:
    return _get_dal().stock_detail(symbol, market)


# ─── 新增 3 个函数 ─────────────────────────────────────

def news(
    keyword: str | None = None,
    source: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    return _get_dal().news(keyword, source, category, page, page_size)


def factors(
    symbol: str,
    factor_names: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    return _get_dal().factors(symbol, factor_names, start, end)


def search_knowledge(query_embedding: list[float], limit: int = 10) -> list[dict]:
    return _get_dal().search_knowledge(query_embedding, limit)
