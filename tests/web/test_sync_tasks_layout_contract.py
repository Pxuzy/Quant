from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def sync_tasks_page_source() -> str:
    return (ROOT_DIR / "frontend/src/pages/data-system/sync-tasks/SyncTasksPage.tsx").read_text(encoding="utf-8")


def styles_source() -> str:
    return (ROOT_DIR / "frontend/src/styles.css").read_text(encoding="utf-8")


def market_data_types_source() -> str:
    return (ROOT_DIR / "frontend/src/features/market-data/types.ts").read_text(encoding="utf-8")


def sync_console_panel_source() -> str:
    return (ROOT_DIR / "frontend/src/pages/data-system/sync-tasks/components/SyncConsolePanel.tsx").read_text(encoding="utf-8")


def sync_operation_tabs_source() -> str:
    return (ROOT_DIR / "frontend/src/pages/data-system/sync-tasks/components/SyncOperationTabs.tsx").read_text(encoding="utf-8")


def sync_task_detail_drawer_source() -> str:
    return (ROOT_DIR / "frontend/src/pages/data-system/sync-tasks/components/TaskDetailDrawer.tsx").read_text(encoding="utf-8")


def test_sync_tasks_page_uses_tabbed_operations_layout():
    source = sync_tasks_page_source()

    assert "SyncConsolePanelCard" in source
    assert "SyncOperationTabsCard" in source
    assert "SyncTaskDetailDrawer" in source
    assert 'className="sync-tracking-card stock-detail-panel"' in source
    assert "items={trackingItems}" in source
    assert 'className="sync-command-row"' not in source
    assert 'className="sync-table-card"' not in source
    assert 'title="创建同步任务"' not in source
    assert 'title="同步控制台"' not in source


def test_sync_tasks_layout_has_compact_panel_styles():
    page_source = sync_operation_tabs_source()
    console_source = sync_console_panel_source()
    drawer_source = sync_task_detail_drawer_source()

    assert 'className="sync-operations-card stock-detail-panel"' in page_source
    assert 'className="sync-console-panel stock-detail-panel"' in console_source
    assert 'className="task-detail-drawer"' in drawer_source
    assert ".sync-console-grid" in styles_source()
    assert ".sync-tracking-card" in styles_source()
    assert ".sync-operation-pane" in styles_source()


def test_sync_tasks_layout_has_mobile_responsive_fallback():
    source = styles_source()

    assert "@media (max-width: 900px)" in source
    assert ".app-sider {" in source
    assert "display: none;" in source
    assert ".workbench {" in source
    assert "min-width: 0;" in source
    assert ".sync-console-grid {" in source
    assert "grid-template-columns: minmax(0, 1fr);" in source
    assert ".sync-console-task-strip {" in source
    assert ".sync-operation-form .ant-col {" in source
    assert "max-width: 100%;" in source


def test_sync_tasks_page_exposes_daily_bar_adjust_type_controls():
    source = sync_tasks_page_source()
    types_source = market_data_types_source()

    assert "formatAdjustType" in source
    assert "DEFAULT_ADJUST_TYPE" in source
    assert "adjustTypeOptions" in source
    assert 'name="adjustType"' in source
    assert "adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE" in source
    assert 'label="复权口径"' in source
    assert "adjust_type?: 'none' | 'qfq' | 'hfq'" in types_source
