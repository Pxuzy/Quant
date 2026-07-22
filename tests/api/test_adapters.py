from __future__ import annotations

from datetime import date

from backend.app.adapters.akshare import AkShareAdapter
from backend.app.adapters.baostock import BaoStockAdapter
from backend.app.adapters.registry import default_adapter_registry
from backend.app.adapters.stock_sdk import StockSdkAdapter, _NodeStockSdkClient


class FakeAkShareClient:
    def stock_info_a_code_name(self):
        return [
            {"code": "600519", "name": "贵州茅台", "listing_date": "2001-08-27"},
            {"code": "000001", "name": "平安银行", "listing_date": "1991-04-03"},
            {"code": "430047", "name": "北交所样本"},
        ]

    def stock_zh_a_hist(self, **kwargs):
        self.daily_query = kwargs
        return [
            {
                "日期": date(2026, 6, 2),
                "股票代码": "600519",
                "开盘": 1306.0,
                "收盘": 1307.22,
                "最高": 1326.36,
                "最低": 1301.0,
                "成交量": 36362,
                "成交额": 4769963104.0,
            },
            {
                "日期": date(2026, 6, 3),
                "股票代码": "600519",
                "开盘": 1304.0,
                "收盘": 1281.91,
                "最高": 1304.0,
                "最低": 1276.0,
                "成交量": 52477,
                "成交额": 6743202681.0,
            },
        ]


class FakeAkShareFallbackClient:
    def __init__(self) -> None:
        self.stock_list_fallback_used = False
        self.daily_fallback_query = None

    def stock_info_a_code_name(self):
        raise RuntimeError("primary stock list unavailable")

    def stock_zh_a_spot_em(self):
        self.stock_list_fallback_used = True
        return [
            {"代码": "600519", "名称": "贵州茅台"},
            {"代码": "000001", "名称": "平安银行"},
        ]

    def stock_zh_a_hist(self, **kwargs):
        raise RuntimeError("primary daily bars unavailable")

    def stock_zh_a_daily(self, **kwargs):
        self.daily_fallback_query = kwargs
        return [
            {
                "date": date(2026, 6, 2),
                "open": 1306.0,
                "high": 1326.36,
                "low": 1301.0,
                "close": 1307.22,
                "volume": 36362,
                "amount": 4769963104.0,
            }
        ]


class FakeBaoStockLoginResult:
    error_code = "0"
    error_msg = ""


class FakeBaoStockResultSet:
    fields = ["code", "code_name", "ipoDate", "outDate", "type", "status"]

    def __init__(self) -> None:
        self._rows = [
            ["sh.600519", "贵州茅台", "2001-08-27", "", "1", "1"],
            ["sz.000001", "平安银行", "1991-04-03", "", "1", "1"],
            ["bj.430047", "北交所样本", "2014-01-24", "", "1", "1"],
        ]
        self._index = -1
        self.error_code = "0"
        self.error_msg = ""

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


class FakeBaoStockDailyResultSet:
    fields = ["date", "code", "open", "high", "low", "close", "preclose", "volume", "amount", "adjustflag"]

    def __init__(self) -> None:
        self._rows = [
            [
                "2026-06-01",
                "sh.600519",
                "1660.00",
                "1680.00",
                "1650.00",
                "1675.00",
                "1662.00",
                "123456",
                "206789000",
                "3",
            ],
            [
                "2026-06-02",
                "sh.600519",
                "1675.00",
                "1691.00",
                "1668.00",
                "1688.00",
                "1675.00",
                "234567",
                "395678000",
                "3",
            ],
        ]
        self._index = -1
        self.error_code = "0"
        self.error_msg = ""

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


class FakeBaoStockCalendarResultSet:
    fields = ["calendar_date", "is_trading_day"]

    def __init__(self) -> None:
        self._rows = [
            ["2026-06-01", "1"],
            ["2026-06-02", "1"],
            ["2026-06-06", "0"],
        ]
        self._index = -1
        self.error_code = "0"
        self.error_msg = ""

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


class FakeBaoStockIndustryResultSet:
    fields = ["updateDate", "code", "code_name", "industry", "industryClassification"]

    def __init__(self) -> None:
        self._rows = [
            ["2026-06-22", "sh.600519", "贵州茅台", "C15酒、饮料和精制茶制造业", "证监会行业分类"],
            ["2026-06-22", "sz.000001", "平安银行", "J66货币金融服务", "证监会行业分类"],
            ["2026-06-22", "bj.430047", "北交所样本", "", "证监会行业分类"],
        ]
        self._index = -1
        self.error_code = "0"
        self.error_msg = ""

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


class FakeBaoStockClient:
    def __init__(self) -> None:
        self.logged_out = False
        self.daily_query = None

    def login(self):
        return FakeBaoStockLoginResult()

    def logout(self):
        self.logged_out = True

    def query_stock_basic(self):
        return FakeBaoStockResultSet()

    def query_stock_industry(self):
        return FakeBaoStockIndustryResultSet()

    def query_history_k_data_plus(self, code, fields, **kwargs):
        self.daily_query = {"code": code, "fields": fields, **kwargs}
        return FakeBaoStockDailyResultSet()

    def query_trade_dates(self, **kwargs):
        self.calendar_query = kwargs
        return FakeBaoStockCalendarResultSet()


class FlakyBaoStockClient(FakeBaoStockClient):
    def __init__(self) -> None:
        super().__init__()
        self.stock_basic_attempts = 0
        self.logout_count = 0

    def logout(self):
        self.logout_count += 1
        self.logged_out = True

    def query_stock_basic(self):
        self.stock_basic_attempts += 1
        if self.stock_basic_attempts == 1:
            raise RuntimeError("网络接收错误。")
        return FakeBaoStockResultSet()


class FakeTushareClient:
    def stock_basic(self, **kwargs):
        return [
            {
                "ts_code": "600519.SH",
                "symbol": "600519",
                "name": "贵州茅台",
                "industry": "白酒",
                "list_date": "20010827",
            },
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "industry": "银行",
                "list_date": "19910403",
            },
            {
                "ts_code": "430047.BJ",
                "symbol": "430047",
                "name": "北交所样本",
                "industry": "软件",
                "list_date": "20140124",
            },
        ]

    def daily(self, **kwargs):
        return [
            {
                "ts_code": "600519.SH",
                "trade_date": "20260601",
                "open": 1660.0,
                "high": 1680.0,
                "low": 1650.0,
                "close": 1675.0,
                "pre_close": 1662.0,
                "vol": 123456.0,
                "amount": 206789.0,
            },
            {
                "ts_code": "600519.SH",
                "trade_date": "20260602",
                "open": 1675.0,
                "high": 1691.0,
                "low": 1668.0,
                "close": 1688.0,
                "pre_close": 1675.0,
                "vol": 234567.0,
                "amount": 395678.0,
            },
        ]

    def trade_cal(self, **kwargs):
        return [
            {"cal_date": "20260601", "is_open": 1},
            {"cal_date": "20260602", "is_open": 1},
            {"cal_date": "20260606", "is_open": 0},
        ]


class FakeADataInfoClient:
    def all_code(self):
        return [
            {"stock_code": "600519", "short_name": "贵州茅台", "exchange": "SH", "list_date": "2001-08-27"},
            {"stock_code": "000001", "short_name": "平安银行", "exchange": "SZ", "list_date": "1991-04-03"},
            {"stock_code": "430047", "short_name": "北交所样本", "exchange": "BJ", "list_date": "2014-01-24"},
        ]


class FakeADataMarketClient:
    def __init__(self) -> None:
        self.query = None

    def get_market(self, **kwargs):
        self.query = kwargs
        return [
            {
                "stock_code": "600519",
                "trade_date": "2026-06-01",
                "open": 1660.0,
                "high": 1680.0,
                "low": 1650.0,
                "close": 1675.0,
                "volume": 123456,
                "amount": 206789000.0,
            },
            {
                "stock_code": "600519",
                "trade_date": "2026-06-02",
                "open": 1675.0,
                "high": 1691.0,
                "low": 1668.0,
                "close": 1688.0,
                "volume": 234567,
                "amount": 395678000.0,
            },
        ]


class FakeADataClient:
    def __init__(self) -> None:
        self.stock = type(
            "StockNamespace",
            (),
            {"info": FakeADataInfoClient(), "market": FakeADataMarketClient()},
        )()


class FakeStockSdkCodesClient:
    def __init__(self) -> None:
        self.query = None

    def cn(self, **kwargs):
        self.query = kwargs
        return [
            {"code": "600519", "name": "贵州茅台", "exchange": "SSE", "listDate": "2001-08-27"},
            {"code": "000001", "name": "平安银行", "exchange": "SZSE", "listDate": "1991-04-03"},
            {"code": "430047", "name": "北交所样本", "exchange": "BSE", "listDate": "2014-01-24"},
        ]


class FakeStockSdkKlineClient:
    def __init__(self) -> None:
        self.query = None

    def cn(self, **kwargs):
        self.query = kwargs
        return [
            {
                "code": "600519",
                "date": "2026-06-01",
                "open": 1660.0,
                "high": 1680.0,
                "low": 1650.0,
                "close": 1675.0,
                "preClose": 1662.0,
                "volume": 123456,
                "amount": 206789000.0,
            },
            {
                "code": "600519",
                "date": "2026-06-02",
                "open": 1675.0,
                "high": 1691.0,
                "low": 1668.0,
                "close": 1688.0,
                "preClose": 1675.0,
                "volume": 234567,
                "amount": 395678000.0,
            },
        ]


class FakeStockSdkClient:
    def __init__(self) -> None:
        self.codes = FakeStockSdkCodesClient()
        self.kline = FakeStockSdkKlineClient()


def test_akshare_adapter_normalizes_stock_list_from_optional_client():
    adapter = AkShareAdapter(client=FakeAkShareClient())

    health = adapter.health_check()
    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert health.healthy is True
    assert len(normalized) == 3
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].market == "A_SHARE"
    assert normalized[0].name == "贵州茅台"
    assert normalized[0].listing_date == date(2001, 8, 27)
    assert normalized[0].source == "akshare"
    assert normalized[1].exchange == "SZSE"
    assert normalized[2].exchange == "BSE"


def test_akshare_adapter_fetches_and_normalizes_daily_bars():
    client = FakeAkShareClient()
    adapter = AkShareAdapter(client=client)

    raw_records = adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 2),
        end_date=date(2026, 6, 3),
    )
    normalized = adapter.normalize_daily_bars(raw_records)

    assert client.daily_query["symbol"] == "600519"
    assert client.daily_query["start_date"] == "20260602"
    assert client.daily_query["adjust"] == ""
    assert len(normalized) == 2
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].trade_date == date(2026, 6, 2)
    assert normalized[0].close == 1307.22
    assert normalized[0].volume == 36362.0
    assert normalized[0].amount == 4769963104.0
    assert normalized[0].source == "akshare"


def test_akshare_adapter_falls_back_within_provider_for_stock_list_and_daily_bars():
    client = FakeAkShareFallbackClient()
    adapter = AkShareAdapter(client=client)

    stock_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized_stocks = adapter.normalize_stock_list(stock_records)
    daily_records = adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 2),
        end_date=date(2026, 6, 2),
    )
    normalized_daily = adapter.normalize_daily_bars(daily_records)

    assert client.stock_list_fallback_used is True
    assert normalized_stocks[0].symbol == "600519"
    assert client.daily_fallback_query["symbol"] == "sh600519"
    assert client.daily_fallback_query["adjust"] == ""
    assert normalized_daily[0].symbol == "600519"
    assert normalized_daily[0].close == 1307.22


def test_akshare_adapter_maps_adjust_type_to_provider_adjust_parameter():
    client = FakeAkShareClient()
    adapter = AkShareAdapter(client=client)

    adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 2),
        end_date=date(2026, 6, 3),
        adjust_type="qfq",
    )

    assert client.daily_query["adjust"] == "qfq"


def test_akshare_adapter_reports_missing_optional_dependency_as_unavailable(monkeypatch):
    adapter = AkShareAdapter()

    def fake_get_client():
        raise ModuleNotFoundError("No module named 'openpyxl'")

    monkeypatch.setattr(adapter, "_get_client", fake_get_client)

    health = adapter.health_check()

    assert health.healthy is False
    assert health.status == "unavailable"
    assert "openpyxl" in health.message


def test_stock_sdk_adapter_reports_missing_optional_dependency_as_unavailable(monkeypatch):
    adapter = StockSdkAdapter()

    def fake_get_client():
        raise ModuleNotFoundError("No module named 'stock_sdk'")

    monkeypatch.setattr(adapter, "_get_client", fake_get_client)

    health = adapter.health_check()

    assert health.healthy is False
    assert health.status == "unavailable"
    assert "stock_sdk" in health.message


def test_baostock_adapter_normalizes_stock_list_from_optional_client():
    client = FakeBaoStockClient()
    adapter = BaoStockAdapter(client=client)

    health = adapter.health_check()
    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert health.healthy is True
    assert client.logged_out is True
    assert len(normalized) == 3
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].name == "贵州茅台"
    assert normalized[0].industry == "酒、饮料和精制茶制造业"
    assert normalized[0].listing_date == date(2001, 8, 27)
    assert normalized[0].source == "baostock"
    assert normalized[1].exchange == "SZSE"
    assert normalized[1].industry == "货币金融服务"
    assert normalized[2].exchange == "BSE"
    assert normalized[2].industry is None


def test_baostock_adapter_retries_transient_stock_list_fetch_failure():
    client = FlakyBaoStockClient()
    adapter = BaoStockAdapter(client=client)

    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert client.stock_basic_attempts == 2
    assert client.logout_count == 2
    assert normalized[0].symbol == "600519"
