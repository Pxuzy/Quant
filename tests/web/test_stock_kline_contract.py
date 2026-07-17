from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def stock_kline_chart_source() -> str:
    return (ROOT_DIR / "frontend/src/shared/components/StockKlineChart.tsx").read_text(encoding="utf-8")


def stock_detail_page_source() -> str:
    return (ROOT_DIR / "frontend/src/pages/data-system/stocks/StockDetailPage.tsx").read_text(encoding="utf-8")


def stock_detail_utils_source() -> str:
    return (ROOT_DIR / "frontend/src/pages/data-system/stocks/components/utils.ts").read_text(encoding="utf-8")


def market_data_api_source() -> str:
    return (ROOT_DIR / "frontend/src/features/market-data/api.ts").read_text(encoding="utf-8")


def test_stock_detail_passes_daily_bars_to_kline_chart():
    source = stock_detail_page_source()

    assert "const klineRows = useMemo(() => sortedRows.map(dailyBarToKLine), [sortedRows]);" in source
    assert "data={klineRows}" in source
    assert "dataLoading={dailyBarsQuery.isLoading}" in source


def test_stock_kline_uses_external_data_without_fetching_legacy_endpoint():
    source = stock_kline_chart_source()

    assert "data?: KLine[]" in source
    assert "if (data) {" in source
    assert "setKlineData(data);" in source
    assert "if (data) return;" in source


def test_daily_bars_query_does_not_abort_slow_chart_fetches():
    source = market_data_api_source()

    assert "queryFn: () => fetchDailyBars(params)" in source
    assert "queryFn: ({ signal }) => fetchDailyBars(params, signal)" not in source


def test_stock_kline_loads_full_history_without_range_state():
    source = stock_kline_chart_source()

    assert "const KLINE_HISTORY_LIMIT = 10000;" in source
    assert "historyLimit = KLINE_HISTORY_LIMIT" in source
    assert "fetchKline(fullCode, period, historyLimit, signal)" in source
    assert "const [range, setRange]" not in source


def test_stock_kline_omits_range_controls():
    source = stock_kline_chart_source()

    assert "stock-kline-period-cards" in source
    assert "stock-kline-control-card" in source
    assert "stock-kline-range-cards" not in source
    assert "RANGE_OPTIONS" not in source
    assert "visibleCountFromRange" not in source


def test_stock_detail_uses_normalized_symbol_for_stock_identity():
    source = stock_detail_page_source()
    utils_source = stock_detail_utils_source()

    assert "const rawSymbol = params.symbol;" in source
    assert "const symbol = normalizeStockRouteSymbol(rawSymbol);" in source
    assert "const displayCode = rawSymbol.toUpperCase();" in source
    assert "const displayTitle = stock?.name ? `${stock.name} ${displayCode}` : displayCode;" in source
    assert "useStockQuery(symbol, market)" in source
    assert "title={displayTitle}" in source
    assert "export const DETAIL_KLINE_HISTORY_LIMIT = 30000;" in utils_source
    assert "historyLimit={DETAIL_KLINE_HISTORY_LIMIT}" in source


def test_stock_kline_has_left_scale_and_dense_line_mode():
    source = stock_kline_chart_source()

    assert "const LINE_MODE_VISIBLE_YEARS = 4;" in source
    assert "const CANDLE_MODE_VISIBLE_YEARS = 3.75;" in source
    assert "leftPriceScale:" in source
    assert "priceScaleId: 'left'" in source
    assert "subscribeVisibleLogicalRangeChange" in source
    assert "getVisibleYears(data, visibleRange.from, visibleRange.to)" in source
    assert "getNextKlineViewMode(klineViewModeRef.current, visibleYears)" in source
    assert "candleSeries.applyOptions({ visible: nextMode === 'candles' })" in source
    assert "closeLineSeries.applyOptions({ visible: nextMode === 'line' })" in source
    assert "setKlineViewMode" not in source
    assert "LineSeries" in source
