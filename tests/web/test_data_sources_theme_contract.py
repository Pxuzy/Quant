from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def data_sources_page_source() -> str:
    return (ROOT_DIR / "apps/web/src/pages/data-system/data-sources/DataSourcesPage.tsx").read_text(encoding="utf-8")


def test_data_sources_cards_use_antd_v5_styles_api():
    source = data_sources_page_source()

    assert "bodyStyle={{ padding: 0 }}" not in source
    assert "styles={{ body: { padding: 0 } }}" in source
