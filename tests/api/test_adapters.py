from __future__ import annotations

from datetime import date

from apps.api.adapters.adata import ADataAdapter
from apps.api.adapters.akshare import AkShareAdapter
from apps.api.adapters.baostock import BaoStockAdapter
from apps.api.adapters.registry import default_adapter_registry
from apps.api.adapters.stock_sdk import StockSdkAdapter, _NodeStockSdkClient
from apps.api.adapters.tushare import TushareAdapter


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
            ["2026-06-01", "sh.600519", "1660.00", "1680.00", "1650.00", "1675.00", "1662.00", "123456", "206789000", "3"],
            ["2026-06-02", "sh.600519", "1675.00", "1691.00", "1668.00", "1688.00", "1675.00", "234567", "395678000", "3"],
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
            {"ts_code": "600519.SH", "symbol": "600519", "name": "贵州茅台", "industry": "白酒", "list_date": "20010827"},
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "industry": "银行", "list_date": "19910403"},
            {"ts_code": "430047.BJ", "symbol": "430047", "name": "北交所样本", "industry": "软件", "list_date": "20140124"},
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
    assert normalized_daily[0].symbol == "600519"
    assert normalized_daily[0].close == 1307.22


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
    assert normalized[0].listing_date == date(2001, 8, 27)
    assert normalized[0].source == "baostock"
    assert normalized[1].exchange == "SZSE"
    assert normalized[2].exchange == "BSE"


def test_baostock_adapter_retries_transient_stock_list_fetch_failure():
    client = FlakyBaoStockClient()
    adapter = BaoStockAdapter(client=client)

    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert client.stock_basic_attempts == 2
    assert client.logout_count == 2
    assert normalized[0].symbol == "600519"


def test_baostock_adapter_fetches_and_normalizes_daily_bars():
    client = FakeBaoStockClient()
    adapter = BaoStockAdapter(client=client)

    raw_records = adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )
    normalized = adapter.normalize_daily_bars(raw_records)

    assert client.logged_out is True
    assert client.daily_query["code"] == "sh.600519"
    assert client.daily_query["start_date"] == "2026-06-01"
    assert len(normalized) == 2
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].market == "A_SHARE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].close == 1675.0
    assert normalized[0].source == "baostock"


def test_baostock_adapter_fetches_and_normalizes_trading_calendar():
    client = FakeBaoStockClient()
    adapter = BaoStockAdapter(client=client)

    raw_records = adapter.fetch_trading_calendar(
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 6),
    )
    normalized = adapter.normalize_trading_calendar(raw_records, market="A_SHARE")

    assert client.logged_out is True
    assert client.calendar_query["start_date"] == "2026-06-01"
    assert len(normalized) == 3
    assert normalized[0].market == "A_SHARE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].is_open is True
    assert normalized[2].is_open is False
    assert normalized[0].source == "baostock"


def test_tushare_adapter_requires_token_but_normalizes_with_client_injection():
    adapter = TushareAdapter(client=FakeTushareClient())

    health = adapter.health_check()
    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert adapter.requires_token is True
    assert adapter.default_enabled is False
    assert health.healthy is True
    assert len(normalized) == 3
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].industry == "白酒"
    assert normalized[0].listing_date == date(2001, 8, 27)
    assert normalized[0].source == "tushare"
    assert normalized[1].exchange == "SZSE"
    assert normalized[2].exchange == "BSE"


def test_tushare_adapter_fetches_and_normalizes_daily_bars():
    adapter = TushareAdapter(client=FakeTushareClient())

    raw_records = adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )
    normalized = adapter.normalize_daily_bars(raw_records)

    assert len(normalized) == 2
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].pre_close == 1662.0
    assert normalized[0].volume == 123456.0
    assert normalized[0].source == "tushare"


def test_tushare_adapter_fetches_and_normalizes_trading_calendar():
    adapter = TushareAdapter(client=FakeTushareClient())

    raw_records = adapter.fetch_trading_calendar(
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 6),
    )
    normalized = adapter.normalize_trading_calendar(raw_records, market="A_SHARE")

    assert len(normalized) == 3
    assert normalized[0].market == "A_SHARE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].is_open is True
    assert normalized[2].is_open is False
    assert normalized[0].source == "tushare"


def test_adata_adapter_normalizes_stock_list_from_optional_client():
    adapter = ADataAdapter(client=FakeADataClient())

    health = adapter.health_check()
    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert adapter.requires_token is False
    assert adapter.default_enabled is True
    assert health.healthy is True
    assert len(normalized) == 3
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].name == "贵州茅台"
    assert normalized[0].listing_date == date(2001, 8, 27)
    assert normalized[0].source == "adata"
    assert normalized[1].exchange == "SZSE"
    assert normalized[2].exchange == "BSE"


def test_adata_adapter_fetches_and_normalizes_daily_bars():
    client = FakeADataClient()
    adapter = ADataAdapter(client=client)

    raw_records = adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )
    normalized = adapter.normalize_daily_bars(raw_records)

    assert client.stock.market.query["stock_code"] == "600519"
    assert client.stock.market.query["start_date"] == "2026-06-01"
    assert len(normalized) == 2
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].close == 1675.0
    assert normalized[0].amount == 206789000.0
    assert normalized[0].source == "adata"


def test_stock_sdk_adapter_normalizes_stock_list_from_optional_client():
    adapter = StockSdkAdapter(client=FakeStockSdkClient())

    health = adapter.health_check()
    raw_records = adapter.fetch_stock_list(market="A_SHARE")
    normalized = adapter.normalize_stock_list(raw_records)

    assert adapter.requires_token is False
    assert adapter.default_enabled is False
    assert health.healthy is True
    assert len(normalized) == 3
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].name == "贵州茅台"
    assert normalized[0].listing_date == date(2001, 8, 27)
    assert normalized[0].source == "stock_sdk"
    assert normalized[1].exchange == "SZSE"
    assert normalized[2].exchange == "BSE"


def test_stock_sdk_adapter_fetches_and_normalizes_daily_bars():
    client = FakeStockSdkClient()
    adapter = StockSdkAdapter(client=client)

    raw_records = adapter.fetch_daily_bars(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )
    normalized = adapter.normalize_daily_bars(raw_records)

    assert client.kline.query["symbol"] == "600519"
    assert client.kline.query["start_date"] == "2026-06-01"
    assert len(normalized) == 2
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].pre_close == 1662.0
    assert normalized[0].volume == 123456.0
    assert normalized[0].source == "stock_sdk"


def test_stock_sdk_adapter_normalizes_stock_sdk_v2_daily_bar_shape():
    adapter = StockSdkAdapter(client=FakeStockSdkClient())

    normalized = adapter.normalize_daily_bars(
        [
            {
                "date": "2026-06-01",
                "timestamp": 1780243200000,
                "tz": "Asia/Shanghai",
                "code": "600519",
                "open": 1660,
                "close": 1675,
                "high": 1680,
                "low": 1650,
                "volume": 123456,
                "amount": 206789000,
                "changePercent": 1.2,
            }
        ]
    )

    assert len(normalized) == 1
    assert normalized[0].symbol == "600519"
    assert normalized[0].exchange == "SSE"
    assert normalized[0].trade_date == date(2026, 6, 1)
    assert normalized[0].close == 1675.0
    assert normalized[0].amount == 206789000.0
    assert normalized[0].source == "stock_sdk"


def test_stock_sdk_node_bridge_supports_legacy_sdk_exports(tmp_path, monkeypatch):
    package_json = tmp_path / "package.json"
    package_json.write_text('{"type":"commonjs"}', encoding="utf-8")
    stock_sdk_dir = tmp_path / "node_modules" / "stock-sdk"
    stock_sdk_dir.mkdir(parents=True)
    (stock_sdk_dir / "index.js").write_text(
        """
class StockSDK {
  async getAShareCodeList() {
    return ["sh600519", "sz000001"];
  }

  async getHistoryKline(symbol, options) {
    return [{
      code: symbol,
      date: options.startDate,
      open: 1660,
      high: 1680,
      low: 1650,
      close: 1675,
      volume: 123456,
      amount: 206789000
    }];
  }
}

module.exports = { StockSDK };
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("STOCK_SDK_CWD", str(tmp_path))
    client = _NodeStockSdkClient()

    assert client.health_check() == {"hasCodes": True, "hasKline": True}
    assert client.codes.cn() == ["sh600519", "sz000001"]
    bars = client.kline.cn(symbol="600519", start_date="2026-06-01", end_date="2026-06-02")
    assert bars[0]["code"] == "600519"
    assert bars[0]["date"] == "20260601"


def test_stock_sdk_node_bridge_supports_v2_namespace_exports(tmp_path, monkeypatch):
    package_json = tmp_path / "package.json"
    package_json.write_text('{"type":"commonjs"}', encoding="utf-8")
    stock_sdk_dir = tmp_path / "node_modules" / "stock-sdk"
    stock_sdk_dir.mkdir(parents=True)
    (stock_sdk_dir / "index.js").write_text(
        """
module.exports = {
  codes: {
    async cn(params) {
      return { data: [{ code: "600519", name: "贵州茅台", exchange: "SH" }] };
    }
  },
  kline: {
    async cn(params) {
      return { records: [{
        code: params.symbol,
        tradeDate: params.startDate,
        openPrice: 1660,
        highPrice: 1680,
        lowPrice: 1650,
        closePrice: 1675,
        vol: 123456,
        turnover: 206789000
      }] };
    }
  }
};
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("STOCK_SDK_CWD", str(tmp_path))
    client = _NodeStockSdkClient()

    assert client.health_check() == {"hasCodes": True, "hasKline": True}
    stocks = client.codes.cn(market="A_SHARE")
    bars = client.kline.cn(symbol="600519", startDate="2026-06-01", endDate="2026-06-02")
    assert stocks["data"][0]["code"] == "600519"
    assert bars["records"][0]["tradeDate"] == "2026-06-01"


def test_stock_sdk_node_bridge_prefers_usable_constructor_over_default_export(tmp_path, monkeypatch):
    package_json = tmp_path / "package.json"
    package_json.write_text('{"type":"commonjs"}', encoding="utf-8")
    stock_sdk_dir = tmp_path / "node_modules" / "stock-sdk"
    stock_sdk_dir.mkdir(parents=True)
    (stock_sdk_dir / "index.js").write_text(
        """
class StockSDK {
  constructor() {
    this.codes = {
      cn: async () => [{ code: "600519", name: "贵州茅台", exchange: "SH" }]
    };
    this.kline = {
      cn: async (symbol, options) => [{
        code: symbol,
        date: options.startDate,
        open: 1660,
        high: 1680,
        low: 1650,
        close: 1675,
        volume: 123456,
        amount: 206789000
      }]
    };
  }
}

module.exports = {
  default: { packageName: "stock-sdk" },
  StockSDK
};
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("STOCK_SDK_CWD", str(tmp_path))
    client = _NodeStockSdkClient()

    assert client.health_check() == {"hasCodes": True, "hasKline": True}
    bars = client.kline.cn(symbol="600519", start_date="2026-06-01", end_date="2026-06-02")
    assert bars[0]["code"] == "600519"
    assert bars[0]["date"] == "20260601"


def test_stock_sdk_node_bridge_returns_compact_upstream_error(tmp_path, monkeypatch):
    package_json = tmp_path / "package.json"
    package_json.write_text('{"type":"commonjs"}', encoding="utf-8")
    stock_sdk_dir = tmp_path / "node_modules" / "stock-sdk"
    stock_sdk_dir.mkdir(parents=True)
    (stock_sdk_dir / "index.js").write_text(
        """
class StockSDK {
  constructor() {
    this.codes = { cn: async () => ["sh600519"] };
    this.kline = {
      cn: async () => {
        const error = new Error("fetch failed");
        error.code = "NETWORK_ERROR";
        error.provider = "eastmoney";
        error.url = "https://91.push2his.eastmoney.com/api/qt/stock/kline/get";
        error.cause = new Error("socket closed");
        throw error;
      }
    };
  }
}

module.exports = { StockSDK };
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("STOCK_SDK_CWD", str(tmp_path))
    client = _NodeStockSdkClient()

    try:
        client.kline.cn(symbol="600519", start_date="2026-06-01", end_date="2026-06-02")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("stock-sdk bridge should surface upstream failure.")

    assert "stock-sdk request failed" in message
    assert "code=NETWORK_ERROR" in message
    assert "provider=eastmoney" in message
    assert "url=https://91.push2his.eastmoney.com/api/qt/stock/kline/get" in message
    assert "Error:" not in message
    assert "at " not in message


def test_registry_filters_known_open_provider_adapters_by_declared_capability():
    registry = default_adapter_registry()

    stock_list_sources = [adapter.code for adapter in registry.list_for_capability("stock_list")]
    daily_bar_sources = [adapter.code for adapter in registry.list_for_capability("daily_bars")]
    calendar_sources = [adapter.code for adapter in registry.list_for_capability("calendars")]

    assert stock_list_sources == ["akshare", "baostock", "adata", "tushare", "stock_sdk"]
    assert daily_bar_sources == ["akshare", "baostock", "adata", "tushare", "stock_sdk"]
    assert calendar_sources == ["baostock", "tushare"]
