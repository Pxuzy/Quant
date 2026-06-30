from __future__ import annotations

import json
from datetime import date

import pytest

from apps.api.adapters.base import NormalizedDailyBar
from apps.api.core.config import reset_settings_cache
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.services.market_service import get_history_kline


@pytest.fixture(autouse=True)
def reset_settings_between_tests():
    reset_settings_cache()
    yield
    reset_settings_cache()


def make_bar(symbol: str, trade_date: date, close: float) -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol=symbol,
        exchange="SSE" if symbol.startswith("6") else "SZSE",
        market="A_SHARE",
        trade_date=trade_date,
        open=close - 0.2,
        high=close + 0.4,
        low=close - 0.5,
        close=close,
        pre_close=None,
        volume=1000.0,
        amount=close * 1000.0,
        adjust_factor=1.0,
        adjust_type="none",
        source="fixture",
    )


def test_market_kline_reads_governed_daily_bars_before_provider(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    reset_settings_cache()
    DailyBarRepository().write_many(
        [
            make_bar("600900", date(2026, 6, 24), 28.3),
            make_bar("600900", date(2026, 6, 25), 28.6),
            make_bar("000001", date(2026, 6, 25), 12.3),
        ]
    )

    def fail_provider_request(url: str, encoding: str = "utf-8") -> str:
        raise AssertionError("provider should not be used when governed daily bars exist")

    monkeypatch.setattr("apps.api.services.market_service._request", fail_provider_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=10000")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2026-06-24", "open": 28.1, "high": 28.7, "close": 28.3, "low": 27.8, "volume": 1000},
        {"date": "2026-06-25", "open": 28.4, "high": 29.0, "close": 28.6, "low": 28.1, "volume": 1000},
    ]


def test_history_kline_normalizes_prefixed_code_for_governed_daily_bars(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    reset_settings_cache()
    DailyBarRepository().write_many(
        [
            make_bar("000001", date(2026, 6, 24), 12.3),
            make_bar("000001", date(2026, 6, 25), 12.6),
        ]
    )

    assert get_history_kline("sz000001", period="day", count=1) == [
        {"date": "2026-06-25", "open": 12.4, "high": 13.0, "close": 12.6, "low": 12.1, "volume": 1000},
    ]


def test_market_kline_handles_provider_empty_data_shape(client, monkeypatch):
    def fake_request(url: str, encoding: str = "utf-8") -> str:
        return json.dumps({"data": []})

    monkeypatch.setattr("apps.api.services.market_service._request", fake_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=5000")

    assert response.status_code == 200
    assert response.json() == []


def test_market_kline_parses_tencent_day_row_order(client, monkeypatch):
    def fake_request(url: str, encoding: str = "utf-8") -> str:
        return json.dumps({
            "data": {
                "sh600900": {
                    "qfqday": [
                        ["2026-06-26", "26.25", "26.72", "26.65", "26.15", "1282652"],
                    ],
                },
            },
        })

    monkeypatch.setattr("apps.api.services.market_service._request", fake_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=1")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2026-06-26", "open": 26.25, "high": 26.65, "close": 26.72, "low": 26.15, "volume": 1282652},
    ]


def test_market_kline_accepts_long_history_request(client, monkeypatch):
    requested_urls: list[str] = []

    def fake_request(url: str, encoding: str = "utf-8") -> str:
        requested_urls.append(url)
        return json.dumps({
            "data": {
                "sh600900": {
                    "qfqday": [
                        ["2026-06-24", "28.10", "28.50", "28.30", "27.90", "1000"],
                        ["2026-06-25", "28.30", "28.80", "28.60", "28.10", "1200"],
                    ],
                },
            },
        })

    monkeypatch.setattr("apps.api.services.market_service._request", fake_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=5000")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2026-06-24", "open": 28.1, "high": 28.3, "close": 28.5, "low": 27.9, "volume": 1000},
        {"date": "2026-06-25", "open": 28.3, "high": 28.6, "close": 28.8, "low": 28.1, "volume": 1200},
    ]
    assert ",800,qfq" in requested_urls[0]


def test_market_kline_splits_provider_requests_for_long_history(client, monkeypatch):
    responses = [
        [["2026-06-24", "28.10", "28.50", "28.30", "27.90", "1000"]],
        [["2023-03-07", "20.10", "20.50", "20.30", "19.90", "900"]],
        [["2019-11-01", "15.10", "15.50", "15.30", "14.90", "800"]],
    ]
    requested_urls: list[str] = []

    def fake_request(url: str, encoding: str = "utf-8") -> str:
        requested_urls.append(url)
        rows = responses.pop(0)
        return json.dumps({"data": {"sh600900": {"qfqday": rows}}})

    monkeypatch.setattr("apps.api.services.market_service._request", fake_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=1601")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2019-11-01", "open": 15.1, "high": 15.3, "close": 15.5, "low": 14.9, "volume": 800},
        {"date": "2023-03-07", "open": 20.1, "high": 20.3, "close": 20.5, "low": 19.9, "volume": 900},
        {"date": "2026-06-24", "open": 28.1, "high": 28.3, "close": 28.5, "low": 27.9, "volume": 1000},
    ]
    assert len(requested_urls) == 3
    assert all(",800,qfq" in url for url in requested_urls[:2])
    assert ",1,qfq" in requested_urls[2]


def test_market_kline_stops_at_provider_empty_page_after_listing_history(client, monkeypatch):
    responses = [
        [["2026-06-24", "28.10", "28.50", "28.30", "27.90", "1000"]],
        [["2023-03-07", "20.10", "20.50", "20.30", "19.90", "900"]],
        [["2019-11-01", "15.10", "15.50", "15.30", "14.90", "800"]],
        [],
    ]
    requested_urls: list[str] = []

    def fake_request(url: str, encoding: str = "utf-8") -> str:
        requested_urls.append(url)
        rows = responses.pop(0)
        return json.dumps({"data": {"sh600900": {"qfqday": rows}}})

    monkeypatch.setattr("apps.api.services.market_service._request", fake_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=10000")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2019-11-01", "open": 15.1, "high": 15.3, "close": 15.5, "low": 14.9, "volume": 800},
        {"date": "2023-03-07", "open": 20.1, "high": 20.3, "close": 20.5, "low": 19.9, "volume": 900},
        {"date": "2026-06-24", "open": 28.1, "high": 28.3, "close": 28.5, "low": 27.9, "volume": 1000},
    ]
    assert len(requested_urls) == 4
