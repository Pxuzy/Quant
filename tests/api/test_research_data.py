from __future__ import annotations

from datetime import date

import pytest

from apps.api.adapters.base import NormalizedDailyBar
from apps.api.services.research_data_service import ResearchDataService


def make_bar(symbol: str, trade_date: date, close: float) -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol=symbol,
        exchange="SSE" if symbol.startswith("6") else "SZSE",
        market="A_SHARE",
        trade_date=trade_date,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        pre_close=None,
        volume=1000.0,
        amount=close * 1000.0,
        adjust_factor=1.0,
        adjust_type="none",
        source="fixture",
    )


def test_bar_reader_returns_governed_daily_bars_with_contract_metadata(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")
    service.daily_bar_repo.write_many(
        [
            make_bar("600519", date(2026, 6, 1), 1680.0),
            make_bar("600519", date(2026, 6, 2), 1690.0),
            make_bar("000001", date(2026, 6, 1), 12.0),
        ]
    )

    payload = service.read_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )

    assert payload["contract"] == {
        "name": "BarReader",
        "dataset": "daily_bars",
        "layer": "silver",
        "adjust_type": "none",
        "source_policy": "governed_only",
    }
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["start_date"] == date(2026, 6, 1)
    assert payload["end_date"] == date(2026, 6, 2)
    assert payload["page"] == 1
    assert payload["page_size"] == 5000
    assert payload["total"] == 2
    assert [item["trade_date"] for item in payload["items"]] == [date(2026, 6, 1), date(2026, 6, 2)]
    assert [item["close"] for item in payload["items"]] == [1680.0, 1690.0]


def test_bar_reader_rejects_blank_symbol(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")

    with pytest.raises(ValueError, match="symbol"):
        service.read_bars(
            symbol=" ",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
        )


def test_bar_reader_rejects_reversed_date_range(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")

    with pytest.raises(ValueError, match="start_date"):
        service.read_bars(
            symbol="600519",
            market="A_SHARE",
            start_date=date(2026, 6, 2),
            end_date=date(2026, 6, 1),
        )


def test_research_bars_api_reads_governed_daily_bars(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    service = ResearchDataService()
    service.daily_bar_repo.write_many(
        [
            make_bar("600519", date(2026, 6, 1), 1680.0),
            make_bar("600519", date(2026, 6, 2), 1690.0),
            make_bar("000001", date(2026, 6, 1), 12.0),
        ]
    )

    response = client.get(
        "/api/research-data/bars",
        params={
            "symbol": "600519",
            "market": "A_SHARE",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "page_size": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"]["name"] == "BarReader"
    assert payload["contract"]["source_policy"] == "governed_only"
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert [item["trade_date"] for item in payload["items"]] == ["2026-06-01"]


def test_research_bars_api_rejects_reversed_date_range(client):
    response = client.get(
        "/api/research-data/bars",
        params={
            "symbol": "600519",
            "market": "A_SHARE",
            "start_date": "2026-06-02",
            "end_date": "2026-06-01",
        },
    )

    assert response.status_code == 400
