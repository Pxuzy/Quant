# 功能矩阵

本文档按产品层级、前端入口、后端 API、核心数据对象和测试覆盖组织功能，便于项目管理和验收。

## 产品层级

| 层级 | 入口 | 用途 |
| --- | --- | --- |
| 股票研究台 | 总控台、股票池、股票详情、新闻汇总、数值数据 | 面向每天查看股票、行情和新闻的研究流程 |
| 数据可信后台 | 数据源管理、同步调度、数据库管理 | 面向数据来源、同步、质量、批次、血缘和缺口修复 |

## 总控台

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 股票研究台 |
| 前端路由 | `/data-system/overview` |
| 页面文件 | `apps/web/src/pages/data-system/overview/DataSystemOverviewPage.tsx` |
| 主要能力 | 系统总览、股票数量、任务概览、数据源健康、质量风险、快捷跳转 |
| 下一步方向 | 从后台总览调整为研究首页：关注股票、行情摘要、新闻事件、数据新鲜度 |
| 相关 API | `/api/database/integration-overview`, `/api/data-quality/overview`, `/api/sync-tasks`, `/api/data-sources`, `/api/datasets` |
| 用户价值 | 快速判断今天能否开始研究，数据是否新鲜，有没有必须先处理的失败或缺口 |

## 新闻汇总

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 股票研究台 |
| 前端路由 | `/data-system/news-summary` |
| 页面文件 | `apps/web/src/pages/data-system/news-summary/NewsSummaryPage.tsx` |
| 当前能力 | 新闻类能力入口和辅助页面 |
| 下一步方向 | 接入真实新闻数据、新闻入库批次、股票关联、来源和日期过滤 |
| 当前边界 | 现阶段不宣称已有真实新闻主链路 |

## 数值数据

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 股票研究台 |
| 前端路由 | `/data-system/numeric-summary` |
| 页面文件 | `apps/web/src/pages/data-system/numeric-summary/NumericSummaryPage.tsx` |
| 当前能力 | 数值数据汇总入口和辅助页面 |
| 下一步方向 | 聚合常用行情字段、成交量、涨跌幅、覆盖状态和后续指标 |
| 当前边界 | 不在阶段一扩展成完整指标或因子平台 |

## 股票池和股票详情

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 股票研究台 |
| 前端路由 | `/data-system/stocks`, `/data-system/stocks/$symbol` |
| 页面文件 | `StocksWorkbenchPage.tsx`, `StockDetailPage.tsx` |
| 主要能力 | 股票列表、搜索、市场/状态筛选、服务端分页、单股详情、日线数据、覆盖、质量、批次 |
| 下一步方向 | 股票详情成为研究主页面，后续聚合新闻事件、常用指标和自选股上下文 |
| 相关 API | `GET /api/stocks`, `GET /api/stocks/{symbol}`, `GET /api/stocks/{symbol}/daily-coverage`, `GET /api/stocks/{symbol}/daily-quality`, `GET /api/stocks/{symbol}/daily-ingest-batches`, `GET /api/market-data/daily-bars/{symbol}`, `POST /api/stocks/sync`, `POST /api/market-data/daily-bars/sync` |
| 数据对象 | `stocks`, `daily_bars`, `ingest_batches`, `data_quality_reports` |
| 测试参考 | `tests/api/test_health_and_stocks.py`, `tests/api/test_market_data.py` |

## 数据源管理

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 数据可信后台 |
| 前端路由 | `/data-system/data-sources` |
| 页面文件 | `DataSourcesPage.tsx` |
| 主要能力 | 数据源列表、能力标签、启用禁用、优先级、健康检查、真实取样、按来源创建同步 |
| 相关 API | `GET /api/data-sources`, `PATCH /api/data-sources/{code}`, `POST /api/data-sources/{code}/health-check`, `POST /api/data-sources/{code}/smoke-test` |
| 数据对象 | `data_sources` |
| 支持来源 | `akshare`, `baostock`, `adata`, `tushare`, `stock_sdk` |
| 测试参考 | `tests/api/test_data_sources.py`, `tests/api/test_adapters.py` |

## 同步调度

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 数据可信后台 |
| 前端路由 | `/data-system/sync-tasks` |
| 页面文件 | `SyncTasksPage.tsx` |
| 主要能力 | 任务列表、筛选、详情、日志、入库批次、runner 状态、定时配置、手动触发 |
| 日线补齐 | 市场级日线缺口补齐默认面向最近半年窗口，并展示补齐范围 |
| 相关 API | `GET /api/sync-tasks`, `GET /api/sync-tasks/{id}`, `GET /api/sync-tasks/{id}/logs`, `GET /api/sync-tasks/{id}/ingest-batches`, `GET /api/sync-tasks/schedules`, `PATCH /api/sync-tasks/schedules/{code}`, `POST /api/sync-tasks/schedules/{code}/trigger`, `GET /api/sync-tasks/runner-status` |
| 任务类型 | `stock_list`, `daily_bars`, `daily_bars_market_repair`, `calendars` |
| Worker | `apps/worker/sync_stocks.py` |
| 测试参考 | `tests/api/test_sync_schedules.py`, `tests/worker/test_sync_stocks_worker.py` |

## 数据库管理

| 项目 | 内容 |
| --- | --- |
| 产品层级 | 数据可信后台 |
| 前端路由 | `/data-system/database` |
| 页面文件 | `DatabaseManagementPage.tsx` |
| 主要能力 | 数据库状态、集成总览、数据集、血缘、质量报告、覆盖缺口、交易日历、市场级补齐入口 |
| 页面边界 | 不承担股票研究主界面职责，只回答数据是否可信、缺什么、怎么修 |
| 相关 API | `GET /api/database/status`, `GET /api/database/integration-overview`, `GET /api/database/lineage`, `GET /api/datasets`, `GET /api/datasets/{name}`, `GET /api/data-quality/overview`, `GET /api/data-quality/reports`, `GET /api/data-quality/check-runs`, `POST /api/data-quality/check`, `GET /api/trading-calendars`, `POST /api/trading-calendars/sync`, `POST /api/market-data/daily-bars/market-repair/preview`, `POST /api/market-data/daily-bars/market-repair` |
| 数据对象 | `datasets`, `trading_calendars`, `data_quality_reports`, `ingest_batches`, Parquet daily bars |
| 测试参考 | `tests/api/test_database_status.py`, `tests/api/test_database_integration.py`, `tests/api/test_datasets.py`, `tests/api/test_data_quality.py`, `tests/api/test_trading_calendars.py` |

## 兼容路由

| 路由 | 当前行为 |
| --- | --- |
| `/data-system/datasets` | 重定向到数据库管理 |
| `/data-system/market-data` | 有 `symbol` 时重定向到股票详情，否则重定向到股票池 |
| `/data-system/trading-calendars` | 重定向到数据库管理 |
| `/data-system/data-quality` | 带质量筛选参数重定向到数据库管理 |
