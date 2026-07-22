from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Iterable

from backend.app.adapters.base import NormalizedDailyBar, NormalizedStock, NormalizedTradingCalendar

SUPPORTED_MARKETS = {"A_SHARE"}
SUPPORTED_EXCHANGES = {"SSE", "SZSE", "BSE"}
LISTED_STATUSES = {"LISTED", "DELISTED", "SUSPENDED"}
ADJUST_TYPES = {"none", "qfq", "hfq"}


def validate_stock_records(records: Iterable[NormalizedStock], *, source: str, market: str) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for index, record in enumerate(records):
        row = _row_label(index, record.symbol)
        _validate_source(errors, row=row, actual=record.source, expected=source)
        _validate_market(errors, row=row, actual=record.market, expected=market)
        _validate_exchange(errors, row=row, exchange=record.exchange)
        if not record.symbol:
            errors.append(f"{row}: symbol is required.")
        if not record.name:
            errors.append(f"{row}: name is required.")
        if record.status not in LISTED_STATUSES:
            errors.append(f"{row}: status '{record.status}' is not supported.")
        key = (record.symbol, record.exchange, record.market)
        if key in seen:
            errors.append(f"{row}: duplicate stock identity {key}.")
        seen.add(key)
    return errors


def validate_daily_bar_records(
    records: Iterable[NormalizedDailyBar],
    *,
    source: str,
    market: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[str]:
    records = list(records)
    if not records:
        return ["no daily bar records returned by provider."]

    errors: list[str] = []
    seen: set[tuple[str, str, str, date, str]] = set()
    for index, record in enumerate(records):
        trade_date_label = record.trade_date.isoformat() if isinstance(record.trade_date, date) else record.trade_date
        row = _row_label(index, f"{record.symbol}/{trade_date_label}")
        _validate_source(errors, row=row, actual=record.source, expected=source)
        _validate_market(errors, row=row, actual=record.market, expected=market)
        _validate_exchange(errors, row=row, exchange=record.exchange)
        if not record.symbol:
            errors.append(f"{row}: symbol is required.")
        if not isinstance(record.trade_date, date):
            errors.append(f"{row}: trade_date must be a date.")
        else:
            if start_date is not None and record.trade_date < start_date:
                errors.append(f"{row}: trade_date must be within requested range.")
            if end_date is not None and record.trade_date > end_date:
                errors.append(f"{row}: trade_date must be within requested range.")
            if record.trade_date > date.today():
                errors.append(f"{row}: trade_date cannot be in the future.")
        for field_name in ("open", "high", "low", "close", "volume", "amount"):
            value = getattr(record, field_name)
            if not isinstance(value, int | float):
                errors.append(f"{row}: {field_name} must be numeric.")
            elif not isfinite(value):
                errors.append(f"{row}: {field_name} must be finite.")
            elif value < 0:
                errors.append(f"{row}: {field_name} cannot be negative.")
        for field_name in ("pre_close", "adjust_factor"):
            value = getattr(record, field_name)
            if value is not None and (not isinstance(value, int | float) or not isfinite(value)):
                errors.append(f"{row}: {field_name} must be finite when provided.")
        ohlc_values = (record.open, record.high, record.low, record.close)
        if all(isinstance(value, int | float) and isfinite(value) for value in ohlc_values):
            if record.high < record.low:
                errors.append(f"{row}: high cannot be lower than low.")
            if record.high < max(record.open, record.close):
                errors.append(f"{row}: high must be >= open and close.")
            if record.low > min(record.open, record.close):
                errors.append(f"{row}: low must be <= open and close.")
        if record.adjust_type not in ADJUST_TYPES:
            errors.append(f"{row}: adjust_type '{record.adjust_type}' is not supported.")
        if record.ingested_at is None:
            errors.append(f"{row}: ingested_at is required.")
        key = (record.symbol, record.exchange, record.market, record.trade_date, record.adjust_type)
        if key in seen:
            errors.append(f"{row}: duplicate daily bar identity {key}.")
        seen.add(key)
    return errors


def validate_calendar_records(records: Iterable[NormalizedTradingCalendar], *, source: str, market: str) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, date]] = set()
    for index, record in enumerate(records):
        row = _row_label(index, record.trade_date.isoformat())
        _validate_source(errors, row=row, actual=record.source, expected=source)
        _validate_market(errors, row=row, actual=record.market, expected=market)
        if not isinstance(record.is_open, bool):
            errors.append(f"{row}: is_open must be bool.")
        key = (record.market, record.trade_date)
        if key in seen:
            errors.append(f"{row}: duplicate calendar identity {key}.")
        seen.add(key)
    return errors


def _validate_source(errors: list[str], *, row: str, actual: str, expected: str) -> None:
    if actual != expected:
        errors.append(f"{row}: source '{actual}' does not match provider '{expected}'.")


def _validate_market(errors: list[str], *, row: str, actual: str, expected: str) -> None:
    if actual != expected:
        errors.append(f"{row}: market '{actual}' does not match requested market '{expected}'.")
    if actual not in SUPPORTED_MARKETS:
        errors.append(f"{row}: market '{actual}' is not supported in phase 1.")


def _validate_exchange(errors: list[str], *, row: str, exchange: str) -> None:
    if exchange not in SUPPORTED_EXCHANGES:
        errors.append(f"{row}: exchange '{exchange}' is not supported.")


def _row_label(index: int, identity: str) -> str:
    return f"row {index + 1} ({identity or 'unknown'})"
