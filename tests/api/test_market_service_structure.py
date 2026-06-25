from apps.api.services import market_service as api_market_service
from quant.services import market_service as legacy_market_service


def _add_stock(db, *, symbol, exchange, name, industry):
    from apps.api.models import Stock

    db.add(
        Stock(
            symbol=symbol,
            exchange=exchange,
            market="A_SHARE",
            name=name,
            status="LISTED",
            industry=industry,
            source="test",
        )
    )


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


def test_sector_stocks_can_be_limited_to_static_board_category(monkeypatch):
    captured_codes = []

    def fake_db_sector_stocks(name):
        raise AssertionError(f"should not query DB industry for static category: {name}")

    def fake_quotes(codes):
        captured_codes.extend(codes)
        return [{"code": code, "name": code, "change_pct": 1.0} for code in codes]

    monkeypatch.setattr(api_market_service, "_db_sector_stocks", fake_db_sector_stocks)
    monkeypatch.setattr(api_market_service, "get_realtime_quotes", fake_quotes)

    rows = api_market_service.get_sector_stocks("人工智能", category="概念板块")

    assert rows
    assert "sz300033" in captured_codes


def test_sector_stocks_prefers_db_for_industry_category(monkeypatch):
    monkeypatch.setattr(api_market_service, "_ensure_ths_industry_boards", lambda: [])
    monkeypatch.setattr(
        api_market_service,
        "_db_board_stocks",
        lambda name, *, category: [{"code": "sh688981", "name": "中芯国际", "sectors": [name]}],
    )

    rows = api_market_service.get_sector_stocks("半导体", category="行业板块")

    assert rows == [{"code": "sh688981", "name": "中芯国际", "sectors": ["半导体"]}]


def test_fetch_ths_industry_members_parses_detail_table(monkeypatch):
    class FakeAk:
        def stock_board_industry_name_ths(self):
            return [{"name": "半导体", "code": "881121"}]

    html = """
    <table>
      <tr><th>序号</th><th>代码</th><th>名称</th></tr>
      <tr><td>1</td><td>688981</td><td>中芯国际</td></tr>
      <tr><td>2</td><td>300782</td><td>卓胜微</td></tr>
    </table>
    """
    monkeypatch.setattr(api_market_service, "_request", lambda *args, **kwargs: html)

    rows = api_market_service._fetch_ths_industry_members(FakeAk(), "半导体")

    assert rows == [
        {"symbol": "688981", "exchange": "SSE", "name": "中芯国际"},
        {"symbol": "300782", "exchange": "SZSE", "name": "卓胜微"},
    ]


def test_fetch_board_members_keeps_ths_rows_when_backup_fails(monkeypatch):
    class FakeAk:
        def stock_board_industry_cons_em(self, symbol):
            raise ConnectionError("backup failed")

    monkeypatch.setattr(api_market_service, "_import_akshare", lambda: FakeAk())
    monkeypatch.setattr(
        api_market_service,
        "_fetch_ths_industry_members",
        lambda ak, name: [{"symbol": "002466", "exchange": "SZSE", "name": "天齐锂业"}],
    )

    rows = api_market_service._fetch_board_members("行业板块", "能源金属")

    assert rows == [{"symbol": "002466", "exchange": "SZSE", "name": "天齐锂业"}]


def test_sector_rankings_returns_board_rows(monkeypatch):
    quote_map = {
        "sz300033": {"code": "sz300033", "name": "同花顺", "price": 88.0, "change_pct": 4.0, "volume": 500, "amount": 4000},
        "sh600570": {"code": "sh600570", "name": "恒生电子", "price": 30.0, "change_pct": -1.0, "volume": 400, "amount": 1200},
        "sh000001": {"code": "sh000001", "name": "上证指数", "price": 4106.25, "change_pct": -1.37, "volume": 0, "amount": 0},
    }

    def fake_quotes(codes):
        return [quote_map[code] for code in codes if code in quote_map]

    monkeypatch.setattr(api_market_service, "get_realtime_quotes", fake_quotes)
    monkeypatch.setattr(api_market_service, "_ensure_ths_industry_boards", lambda: [])

    rows = legacy_market_service.get_sector_rankings(["行业板块", "概念板块", "指数板块"])
    by_name = {row["name"]: row for row in rows}

    assert ["能源金属", "半导体", "元件"] == [row["name"] for row in rows[:3]]
    assert by_name["能源金属"]["category"] == "行业板块"
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
    assert {"人工智能", "新能源车", "光伏"}.issubset({row["name"] for row in rows})


def test_sector_rankings_uses_ths_industry_boards_when_db_empty(client, monkeypatch):
    monkeypatch.setattr(
        api_market_service,
        "_fetch_ths_industry_boards",
        lambda: [
            {
                "name": "能源金属",
                "category": "行业板块",
                "source": "akshare_ths",
                "provider_code": "881169",
                "change_pct": 3.5,
                "up_count": 11,
                "down_count": 2,
                "stock_count": 13,
                "amount": 1200000000,
                "volume": 5500000,
                "net_inflow": 100000000,
                "leader_name": "天齐锂业",
                "leader_price": 42.5,
                "leader_change_pct": 8.8,
            },
            {
                "name": "半导体",
                "category": "行业板块",
                "source": "akshare_ths",
                "provider_code": "881121",
                "change_pct": 2.1,
                "up_count": 40,
                "down_count": 8,
                "stock_count": 48,
                "amount": 2600000000,
                "volume": 12000000,
                "net_inflow": 300000000,
                "leader_name": "中芯国际",
                "leader_price": 55.0,
                "leader_change_pct": 6.2,
            },
            {
                "name": "元件",
                "category": "行业板块",
                "source": "akshare_ths",
                "provider_code": "881126",
                "change_pct": 1.7,
                "up_count": 25,
                "down_count": 10,
                "stock_count": 35,
                "amount": 1800000000,
                "volume": 9000000,
                "net_inflow": 50000000,
                "leader_name": "沪电股份",
                "leader_price": 31.2,
                "leader_change_pct": 5.5,
            },
        ],
    )

    rows = api_market_service.get_sector_rankings(["行业板块"])
    by_name = {row["name"]: row for row in rows}

    assert list(by_name) == ["能源金属", "半导体", "元件"]
    assert {row["category"] for row in rows} == {"行业板块"}
    assert by_name["能源金属"]["stock_count"] == 13
    assert by_name["能源金属"]["leader"]["name"] == "天齐锂业"


def test_sync_ths_industry_boards_updates_stock_industries(client, monkeypatch):
    from apps.api.db.session import SessionLocal
    from apps.api.models import Stock

    db = SessionLocal()
    try:
        _add_stock(db, symbol="600519", exchange="SSE", name="贵州茅台", industry="酒、饮料和精制茶制造业")
        _add_stock(db, symbol="688981", exchange="SSE", name="中芯国际", industry="计算机、通信和其他电子设备制造业")
        _add_stock(db, symbol="002463", exchange="SZSE", name="沪电股份", industry="计算机、通信和其他电子设备制造业")
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        api_market_service,
        "_fetch_ths_industry_boards",
        lambda: [
            {
                "name": "半导体",
                "category": "行业板块",
                "source": "akshare_ths",
                "provider_code": "881121",
                "change_pct": 2.1,
                "up_count": 40,
                "down_count": 8,
                "stock_count": 48,
                "amount": 2600000000,
                "volume": 12000000,
                "net_inflow": 300000000,
                "leader_name": "中芯国际",
                "leader_price": 55.0,
                "leader_change_pct": 6.2,
            },
            {
                "name": "元件",
                "category": "行业板块",
                "source": "akshare_ths",
                "provider_code": "881126",
                "change_pct": 1.7,
                "up_count": 25,
                "down_count": 10,
                "stock_count": 35,
                "amount": 1800000000,
                "volume": 9000000,
                "net_inflow": 50000000,
                "leader_name": "沪电股份",
                "leader_price": 31.2,
                "leader_change_pct": 5.5,
            },
        ],
    )
    monkeypatch.setattr(
        api_market_service,
        "_fetch_board_members",
        lambda category, name: {
            "半导体": [{"symbol": "688981", "exchange": "SSE", "name": "中芯国际"}],
            "元件": [{"symbol": "002463", "exchange": "SZSE", "name": "沪电股份"}],
        }[name],
    )

    result = api_market_service.sync_ths_industry_boards()

    db = SessionLocal()
    try:
        industries = {stock.symbol: stock.industry for stock in db.query(Stock).all()}
    finally:
        db.close()

    assert result["boards_written"] == 2
    assert result["members_written"] == 2
    assert result["stocks_updated"] == 2
    assert industries["688981"] == "半导体"
    assert industries["002463"] == "元件"


def test_sector_stocks_returns_ths_industry_board_constituents(client, monkeypatch):
    from apps.api.db.session import SessionLocal
    from apps.api.repositories.stock_boards import StockBoardRepository

    db = SessionLocal()
    try:
        repo = StockBoardRepository(db)
        repo.upsert_boards([
            {
                "name": "半导体",
                "category": "行业板块",
                "source": "akshare_ths",
                "provider_code": "881121",
                "stock_count": 2,
            }
        ])
        board = repo.get_board(name="半导体", category="行业板块")
        repo.replace_members(
            board=board,
            source="akshare",
            members=[
                {"symbol": "688981", "exchange": "SSE", "name": "中芯国际"},
                {"symbol": "300782", "exchange": "SZSE", "name": "卓胜微"},
            ],
        )
        db.commit()
    finally:
        db.close()

    def fake_quotes(codes):
        assert codes == ["sh688981", "sz300782"]
        return [
            {"code": "sh688981", "name": "中芯国际", "price": 55.0, "change_pct": 2.1, "volume": 100, "amount": 120000},
        ]

    monkeypatch.setattr(api_market_service, "get_realtime_quotes", fake_quotes)

    rows = api_market_service.get_sector_stocks("半导体", category="行业板块")

    assert [row["code"] for row in rows] == ["sh688981", "sz300782"]
    assert rows[0]["sectors"] == ["半导体"]
    assert rows[1]["name"] == "卓胜微"
    assert rows[1]["price"] == 0


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


def test_market_sector_api_passes_board_category(client, monkeypatch):
    captured = {}

    def fake_sector_stocks(name, category=None):
        captured["name"] = name
        captured["category"] = category
        return [{"code": "sz300033", "name": "同花顺"}]

    from apps.api.routers import market

    monkeypatch.setattr(market, "get_sector_stocks", fake_sector_stocks)

    response = client.get("/api/market/sector", params={"name": "人工智能", "category": "概念板块"})

    assert response.status_code == 200
    assert response.json()[0]["code"] == "sz300033"
    assert captured == {"name": "人工智能", "category": "概念板块"}
