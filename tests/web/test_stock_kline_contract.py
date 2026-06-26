from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def stock_page_source() -> str:
    return (ROOT_DIR / "apps/web/src/pages/stock/StockPage.tsx").read_text(encoding="utf-8")


def test_stock_kline_loads_full_history_before_range_view():
    source = stock_page_source()

    assert "const KLINE_HISTORY_LIMIT = 10000;" in source
    assert "fetchKline(fullCode, period, KLINE_HISTORY_LIMIT, signal)" in source
    assert "const [range, setRange] = useState<RangeValue>('全部')" in source


def test_stock_kline_uses_card_style_range_controls():
    source = stock_page_source()

    assert "stock-kline-period-cards" in source
    assert "stock-kline-range-cards" in source
    assert "stock-kline-control-card" in source
