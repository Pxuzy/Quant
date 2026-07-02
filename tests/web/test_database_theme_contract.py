from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def styles_source() -> str:
    return (ROOT_DIR / "apps/web/src/styles.css").read_text(encoding="utf-8")


def test_database_section_nav_uses_theme_surfaces():
    source = styles_source()
    start = source.index(".database-section-nav {")
    end = source.index(".database-section-nav a {")
    block = source[start:end]

    assert "background: var(--app-surface);" in block
    assert "border: 1px solid var(--app-border);" in block
    assert "#fbfdff" not in block
    assert "#e8edf5" not in block
