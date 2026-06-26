from __future__ import annotations

import json


def test_market_kline_handles_provider_empty_data_shape(client, monkeypatch):
    def fake_request(url: str, encoding: str = "utf-8") -> str:
        return json.dumps({"data": []})

    monkeypatch.setattr("apps.api.services.market_service._request", fake_request)

    response = client.get("/api/market/kline?code=sh600900&period=day&count=5000")

    assert response.status_code == 200
    assert response.json() == []


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
        {"date": "2026-06-24", "open": 28.1, "high": 28.5, "close": 28.3, "low": 27.9, "volume": 1000},
        {"date": "2026-06-25", "open": 28.3, "high": 28.8, "close": 28.6, "low": 28.1, "volume": 1200},
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
        {"date": "2019-11-01", "open": 15.1, "high": 15.5, "close": 15.3, "low": 14.9, "volume": 800},
        {"date": "2023-03-07", "open": 20.1, "high": 20.5, "close": 20.3, "low": 19.9, "volume": 900},
        {"date": "2026-06-24", "open": 28.1, "high": 28.5, "close": 28.3, "low": 27.9, "volume": 1000},
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
        {"date": "2019-11-01", "open": 15.1, "high": 15.5, "close": 15.3, "low": 14.9, "volume": 800},
        {"date": "2023-03-07", "open": 20.1, "high": 20.5, "close": 20.3, "low": 19.9, "volume": 900},
        {"date": "2026-06-24", "open": 28.1, "high": 28.5, "close": 28.3, "low": 27.9, "volume": 1000},
    ]
    assert len(requested_urls) == 4
