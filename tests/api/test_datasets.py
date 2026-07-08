from __future__ import annotations

from datetime import date

from backend.app.db.session import SessionLocal
from backend.app.models import Dataset, Stock


def seed_datasets() -> None:
    db = SessionLocal()
    try:
        db.add_all(
            [
                Dataset(
                    name="stocks",
                    layer="silver",
                    storage_type="postgres",
                    schema_json={"symbol": "string", "name": "string"},
                    primary_keys_json=["symbol", "exchange", "market"],
                    partition_keys_json=["market"],
                    source="akshare",
                    row_count=5000,
                    latest_data_date=date(2026, 6, 5),
                    quality_status="good",
                ),
                Dataset(
                    name="daily_bars",
                    layer="silver",
                    storage_type="parquet",
                    path="./storage/lake/silver/daily_bars",
                    schema_json={"symbol": "string", "trade_date": "date", "close": "float"},
                    primary_keys_json=["symbol", "exchange", "market", "trade_date"],
                    partition_keys_json=["market", "trade_date"],
                    source="baostock",
                    row_count=12000,
                    latest_data_date=date(2026, 6, 4),
                    quality_status="good",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_datasets_api_lists_catalog_with_pagination(client):
    seed_datasets()

    response = client.get("/api/datasets", params={"page": 1, "page_size": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["name"] == "daily_bars"
    assert payload["items"][0]["storage_type"] == "parquet"


def test_datasets_api_filters_catalog(client):
    seed_datasets()

    response = client.get("/api/datasets", params={"storage_type": "postgres"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "stocks"
    assert payload["items"][0]["source"] == "akshare"


def test_datasets_api_filters_catalog_by_name_and_layer(client):
    seed_datasets()

    name_response = client.get("/api/datasets", params={"name": "bar"})
    layer_response = client.get("/api/datasets", params={"layer": "silver"})

    assert name_response.status_code == 200
    name_payload = name_response.json()
    assert name_payload["total"] == 1
    assert name_payload["items"][0]["name"] == "daily_bars"

    assert layer_response.status_code == 200
    layer_payload = layer_response.json()
    assert layer_payload["total"] == 2
    assert {item["name"] for item in layer_payload["items"]} == {"stocks", "daily_bars"}


def test_datasets_api_projects_stale_full_security_stock_count_to_common_stock_pool(client):
    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(symbol="600519", exchange="SSE", market="A_SHARE", name="贵州茅台", status="LISTED", source="fixture"),
                Stock(symbol="000001", exchange="SZSE", market="A_SHARE", name="平安银行", status="LISTED", source="fixture"),
                Stock(symbol="430047", exchange="BSE", market="A_SHARE", name="北交所样本", status="LISTED", source="fixture"),
                Stock(symbol="000016", exchange="SSE", market="A_SHARE", name="上证50指数", status="LISTED", source="fixture"),
                Stock(symbol="159001", exchange="SZSE", market="A_SHARE", name="货币ETF", status="LISTED", source="fixture"),
            ]
        )
        db.add(
            Dataset(
                name="stocks",
                layer="silver",
                storage_type="postgres",
                schema_json={"symbol": "string", "name": "string"},
                primary_keys_json=["symbol", "exchange", "market"],
                partition_keys_json=["market"],
                source="baostock",
                row_count=5,
                latest_data_date=date(2026, 6, 17),
                quality_status="good",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/datasets", params={"name": "stocks"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["name"] == "stocks"
    assert payload["items"][0]["row_count"] == 3

    db = SessionLocal()
    try:
        dataset = db.query(Dataset).filter(Dataset.name == "stocks").one()
        assert dataset.row_count == 3
    finally:
        db.close()


def test_datasets_api_returns_dataset_detail(client):
    seed_datasets()

    response = client.get("/api/datasets/daily_bars")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "daily_bars"
    assert payload["layer"] == "silver"
    assert payload["path"] == "./storage/lake/silver/daily_bars"
    assert payload["primary_keys_json"] == ["symbol", "exchange", "market", "trade_date"]
    assert payload["latest_data_date"] == "2026-06-04"


def test_datasets_api_returns_404_for_missing_dataset(client):
    response = client.get("/api/datasets/missing_dataset")

    assert response.status_code == 404
    assert "missing_dataset" in response.json()["detail"]
