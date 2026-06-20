from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("symbol", "exchange", "market", name="uq_stocks_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="LISTED", index=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delisting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    requires_token: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class SyncTask(Base):
    __tablename__ = "sync_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    market: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    logs: Mapped[list["SyncTaskLog"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="SyncTaskLog.id",
    )
    ingest_batches: Mapped[list["IngestBatch"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="IngestBatch.id",
    )


class SyncTaskLog(Base):
    __tablename__ = "sync_task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("sync_tasks.id"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    task: Mapped[SyncTask] = relationship(back_populates="logs")


class SyncSchedule(Base):
    __tablename__ = "sync_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="auto")
    market: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_note: Mapped[str] = mapped_column(Text, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class IngestBatch(Base):
    __tablename__ = "ingest_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("sync_tasks.id"), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    market: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    normalize_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    raw_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_errors_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    task: Mapped[SyncTask] = relationship(back_populates="ingest_batches")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    layer: Mapped[str] = mapped_column(String(32), nullable=False, default="silver")
    storage_type: Mapped[str] = mapped_column(String(32), nullable=False, default="postgres")
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    primary_keys_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    partition_keys_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_data_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class TradingCalendar(Base):
    __tablename__ = "trading_calendars"
    __table_args__ = (UniqueConstraint("market", "trade_date", name="uq_trading_calendars_market_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
