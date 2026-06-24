from apps.api.services import market_service as api_market_service
from quant.services import market_service as legacy_market_service


def test_market_service_legacy_path_reexports_api_service():
    exported_names = [
        "get_history_kline",
        "get_index_quotes",
        "get_news",
        "get_realtime_quotes",
        "get_sector_rankings",
        "get_sector_stocks",
        "search_stock",
    ]

    for name in exported_names:
        assert getattr(legacy_market_service, name) is getattr(api_market_service, name)


def test_sector_stocks_supports_concept_and_index_aliases(monkeypatch):
    captured_codes = []

    def fake_quotes(codes):
        captured_codes.extend(codes)
        return [{"code": code, "name": code, "change_pct": 1.0} for code in codes]

    monkeypatch.setattr(api_market_service, "get_realtime_quotes", fake_quotes)

    concept_rows = legacy_market_service.get_sector_stocks("人工智能")
    index_rows = legacy_market_service.get_sector_stocks("上证指数")

    assert concept_rows
    assert index_rows
    assert "sz300033" in captured_codes
    assert "sh000001" in captured_codes


def test_sector_rankings_returns_board_rows(monkeypatch):
    quote_map = {
        "sh601398": {"code": "sh601398", "name": "工商银行", "price": 6.1, "change_pct": 2.0, "volume": 1000, "amount": 2000},
        "sh601288": {"code": "sh601288", "name": "农业银行", "price": 4.5, "change_pct": 1.0, "volume": 1000, "amount": 1500},
        "sz300033": {"code": "sz300033", "name": "同花顺", "price": 88.0, "change_pct": 4.0, "volume": 500, "amount": 4000},
        "sh600570": {"code": "sh600570", "name": "恒生电子", "price": 30.0, "change_pct": -1.0, "volume": 400, "amount": 1200},
        "sh000001": {"code": "sh000001", "name": "上证指数", "price": 4106.25, "change_pct": -1.37, "volume": 0, "amount": 0},
    }

    def fake_quotes(codes):
        return [quote_map[code] for code in codes if code in quote_map]

    monkeypatch.setattr(api_market_service, "get_realtime_quotes", fake_quotes)

    rows = legacy_market_service.get_sector_rankings(["行业板块", "概念板块", "指数板块"])
    by_name = {row["name"]: row for row in rows}

    assert by_name["银行"]["category"] == "行业板块"
    assert by_name["银行"]["stock_count"] == 2
    assert by_name["银行"]["up_count"] == 2
    assert by_name["银行"]["leader"]["name"] == "工商银行"
    assert by_name["人工智能"]["category"] == "概念板块"
    assert by_name["上证指数"]["category"] == "指数板块"


def test_sector_rankings_filters_one_board_category(monkeypatch):
    def fake_quotes(codes):
        return [
            {
                "code": code,
                "name": code,
                "price": 10.0,
                "change_pct": 1.0,
                "volume": 100,
                "amount": 200,
            }
            for code in codes
        ]

    monkeypatch.setattr(api_market_service, "get_realtime_quotes", fake_quotes)

    rows = legacy_market_service.get_sector_rankings(["概念板块"])

    assert rows
    assert {row["category"] for row in rows} == {"概念板块"}
    assert {row["name"] for row in rows} == {"人工智能", "新能源车", "光伏"}


def test_market_sectors_api_returns_board_rows(client, monkeypatch):
    def fake_rankings(categories=None):
        return [
            {
                "name": "人工智能",
                "category": "概念板块",
                "change_pct": 1.23,
                "up_count": 4,
                "down_count": 2,
                "stock_count": 6,
                "amount": 100000.0,
                "volume": 5000,
                "leader": {"code": "sz300033", "name": "同花顺", "change_pct": 2.5},
            }
        ]

    from apps.api.routers import market

    monkeypatch.setattr(market, "get_sector_rankings", fake_rankings)

    response = client.get("/api/market/sectors", params={"categories": "行业板块,概念板块,指数板块"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "人工智能"
    assert response.json()[0]["category"] == "概念板块"
    assert response.json()[0]["leader"]["name"] == "同花顺"


def test_market_sectors_api_accepts_single_board_category(client, monkeypatch):
    def fake_rankings(categories=None):
        assert categories == ["指数板块"]
        return [
            {
                "name": "上证指数",
                "category": "指数板块",
                "change_pct": -1.37,
                "up_count": 0,
                "down_count": 1,
                "stock_count": 1,
                "amount": 0,
                "volume": 0,
                "leader": {"code": "sh000001", "name": "上证指数", "change_pct": -1.37},
            }
        ]

    from apps.api.routers import market

    monkeypatch.setattr(market, "get_sector_rankings", fake_rankings)

    response = client.get("/api/market/sectors", params={"categories": "指数板块"})

    assert response.status_code == 200
    assert response.json()[0]["category"] == "指数板块"
