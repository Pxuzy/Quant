from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def theme_provider_source() -> str:
    return (ROOT_DIR / "apps/web/src/app/ThemeProvider.tsx").read_text(encoding="utf-8")


def styles_source() -> str:
    return (ROOT_DIR / "apps/web/src/styles.css").read_text(encoding="utf-8")


def app_layout_source() -> str:
    return (ROOT_DIR / "apps/web/src/layouts/AppLayout.tsx").read_text(encoding="utf-8")


def test_app_theme_uses_documented_antd_component_tokens():
    source = theme_provider_source()

    assert "bodyPaddingSM" in source
    assert "headerHeightSM" in source
    assert "cellPaddingBlockSM" in source
    assert "cellPaddingInlineSM" in source
    assert "itemHeight" in source
    assert "itemMarginInline" in source
    assert "defaultShadow" in source
    assert "defaultBg" in source


def test_app_shell_keeps_workbench_visual_contract():
    source = styles_source()

    assert "--app-focus-ring" in source
    assert "--app-surface-muted" in source
    assert "--app-header-height" in source
    assert "repeating-linear-gradient" in source
    assert ".app-shell :where(button, a, input, textarea, select):focus-visible" in source
    assert ".app-sider .ant-menu" in source
    assert "@media (max-width: 360px)" in source
    assert ".app-header .ant-btn > span:not(.ant-btn-icon)" in source
    assert "width: 42px;" in source


def test_app_surfaces_do_not_use_fixed_light_panel_background():
    source = styles_source()

    assert "#fbfdff" not in source
    assert "#edf0f5" not in source
    assert "#e5eaf2" not in source


def test_app_layout_syncs_menu_theme_with_current_mode():
    source = app_layout_source()

    assert "theme={mode}" in source
    assert "background: 'var(--app-surface)'" in source
