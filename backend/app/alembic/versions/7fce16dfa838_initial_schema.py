"""initial_schema — 幂等地创建所有现有表结构。

对于 SQLite 已存在的表仅补漏；对于 PG 全新库，一次性创建全部。
这样无论是从旧 SQLite 升级还是新 PG 建库，都能正常工作。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

# revision identifiers
revision: str = "7fce16dfa838"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_engine() -> Engine:
    """Get the current migration engine."""
    return op.get_bind().engine


def _get_existing_tables() -> set[str]:
    inspector = inspect(_get_engine())
    return set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    engine = bind.engine

    # Register Vector type if on PG
    if engine.dialect.name == "postgresql":
        try:
            from pgvector.sqlalchemy import Vector
            from sqlalchemy.dialects import postgresql
            postgresql.REGISTERED_TYPES.setdefault("vector", Vector)
        except ImportError:
            pass

    existing = _get_existing_tables()
    inspector = inspect(engine)

    def _has_index(table: str, index_name: str) -> bool:
        return any(idx["name"] == index_name for idx in inspector.get_indexes(table))

    def _ensure_index(table: str, index_name: str, columns: tuple[str, ...], unique: bool = False) -> None:
        if not _has_index(table, index_name):
            op.create_index(index_name, table, list(columns), unique=unique)

    # ── stocks ──
    if "stocks" not in existing:
        op.create_table(
            "stocks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("exchange", sa.String(32), nullable=False),
            sa.Column("market", sa.String(32), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="LISTED"),
            sa.Column("industry", sa.String(128), nullable=True),
            sa.Column("listing_date", sa.Date(), nullable=True),
            sa.Column("delisting_date", sa.Date(), nullable=True),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("latest_data_date", sa.Date(), nullable=True),
            sa.Column("data_completeness", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("symbol", "exchange", "market", name="uq_stocks_identity"),
        )

    # Create indexes idempotently
    _ensure_index("stocks", "ix_stocks_symbol", ("symbol",))
    _ensure_index("stocks", "ix_stocks_exchange", ("exchange",))
    _ensure_index("stocks", "ix_stocks_market", ("market",))
    _ensure_index("stocks", "ix_stocks_name", ("name",))
    _ensure_index("stocks", "ix_stocks_status", ("status",))
    _ensure_index("stocks", "ix_stocks_industry", ("industry",))
    _ensure_index("stocks", "ix_stocks_latest_data_date", ("latest_data_date",))
    _ensure_index("stocks", "ix_stocks_data_completeness", ("data_completeness",))

    # ── data_sources ──
    if "data_sources" not in existing:
        op.create_table(
            "data_sources",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("requires_token", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("config_json", sa.JSON(), nullable=False),
            sa.Column("health_status", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )

    # ── stock_boards ──
    if "stock_boards" not in existing:
        op.create_table(
            "stock_boards",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("category", sa.String(32), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("provider_code", sa.String(64), nullable=True),
            sa.Column("change_pct", sa.Float(), nullable=True),
            sa.Column("up_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("down_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stock_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("volume", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("net_inflow", sa.Float(), nullable=True),
            sa.Column("leader_name", sa.String(128), nullable=True),
            sa.Column("leader_price", sa.Float(), nullable=True),
            sa.Column("leader_change_pct", sa.Float(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("category", "name", name="uq_stock_boards_category_name"),
        )

    # ── stock_board_members ──
    if "stock_board_members" not in existing:
        op.create_table(
            "stock_board_members",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("board_id", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("exchange", sa.String(32), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["board_id"], ["stock_boards.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("board_id", "symbol", "exchange", name="uq_stock_board_members_identity"),
        )

    # ── sync_tasks ──
    if "sync_tasks" not in existing:
        op.create_table(
            "sync_tasks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_type", sa.String(64), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("market", sa.String(32), nullable=True),
            sa.Column("symbol", sa.String(32), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("max_symbols", sa.Integer(), nullable=True),
            sa.Column("start_policy", sa.String(32), nullable=True),
            sa.Column("adjust_type", sa.String(16), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("records_read", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # ── sync_task_logs ──
    if "sync_task_logs" not in existing:
        op.create_table(
            "sync_task_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("level", sa.String(16), nullable=False, server_default="info"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["sync_tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # ── sync_schedules ──
    if "sync_schedules" not in existing:
        op.create_table(
            "sync_schedules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("task_type", sa.String(64), nullable=False),
            sa.Column("source", sa.String(64), nullable=False, server_default="auto"),
            sa.Column("market", sa.String(32), nullable=True),
            sa.Column("symbol", sa.String(32), nullable=True),
            sa.Column("cron_expression", sa.String(128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("schedule_note", sa.Text(), nullable=False),
            sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )

    # ── ingest_batches ──
    if "ingest_batches" not in existing:
        op.create_table(
            "ingest_batches",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("dataset_name", sa.String(128), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("requested_source", sa.String(64), nullable=False),
            sa.Column("market", sa.String(32), nullable=True),
            sa.Column("symbol", sa.String(32), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="running"),
            sa.Column("schema_version", sa.String(32), nullable=False, server_default="v1"),
            sa.Column("normalize_version", sa.String(32), nullable=False, server_default="v1"),
            sa.Column("raw_records", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("normalized_records", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("validation_errors_json", sa.JSON(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("quality_status", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["sync_tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # ── datasets ──
    if "datasets" not in existing:
        op.create_table(
            "datasets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("layer", sa.String(32), nullable=False, server_default="silver"),
            sa.Column("storage_type", sa.String(32), nullable=False, server_default="postgres"),
            sa.Column("path", sa.String(512), nullable=True),
            sa.Column("schema_json", sa.JSON(), nullable=False),
            sa.Column("primary_keys_json", sa.JSON(), nullable=False),
            sa.Column("partition_keys_json", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("latest_data_date", sa.Date(), nullable=True),
            sa.Column("quality_status", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    # ── trading_calendars ──
    if "trading_calendars" not in existing:
        op.create_table(
            "trading_calendars",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("market", sa.String(32), nullable=False),
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("is_open", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("market", "trade_date", name="uq_trading_calendars_market_date"),
        )

    # ── data_quality_reports ──
    if "data_quality_reports" not in existing:
        op.create_table(
            "data_quality_reports",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("dataset_name", sa.String(128), nullable=False),
            sa.Column("check_type", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("severity", sa.String(32), nullable=False),
            sa.Column("metric_name", sa.String(128), nullable=False),
            sa.Column("metric_value", sa.String(128), nullable=True),
            sa.Column("expected_value", sa.String(128), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # ── watchlists ──
    if "watchlists" not in existing:
        op.create_table(
            "watchlists",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("user_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    # ── watchlist_items ──
    if "watchlist_items" not in existing:
        op.create_table(
            "watchlist_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("watchlist_id", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("note", sa.String(255), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbol"),
        )

    # ── news_articles ──
    if "news_articles" not in existing:
        op.create_table(
            "news_articles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("title", sa.String(512), nullable=False),
            sa.Column("url", sa.String(1024), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("category", sa.String(64), nullable=True),
            sa.Column("related_symbols", sa.JSON(), nullable=False),
            sa.Column("external_id", sa.String(128), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
            # embedding column added separately for pgvector compatibility
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_news_source_external_id"),
        )

    # ── news_articles embedding (all backends) ──
    if "news_articles" in existing:
        cols = {c["name"] for c in inspector.get_columns("news_articles")}
        if "embedding" not in cols:
            if engine.dialect.name == "postgresql":
                op.add_column("news_articles", sa.Column("embedding", sa.LargeBinary(), nullable=True))
            else:
                op.add_column("news_articles", sa.Column("embedding", sa.JSON(), nullable=True))


def _get_recent_inspector(engine):
    """Get a fresh inspector — needed because op.get_bind().engine may cache old schema."""
    from sqlalchemy import create_engine
    from sqlalchemy import inspect as sa_inspect
    url = engine.url.render_as_string(hide_password=False)
    temp_engine = create_engine(url)
    try:
        return sa_inspect(temp_engine)
    finally:
        temp_engine.dispose()


def downgrade() -> None:
    """Drop all tables (reverse order for FK compliance)."""
    tables = [
        "watchlist_items",
        "watchlists",
        "news_articles",
        "data_quality_reports",
        "trading_calendars",
        "ingest_batches",
        "sync_schedules",
        "sync_task_logs",
        "sync_tasks",
        "stock_board_members",
        "stock_boards",
        "datasets",
        "data_sources",
        "stocks",
    ]
    for table in tables:
        op.drop_table(table, if_exists=True)
