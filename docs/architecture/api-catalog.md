# API 目录

本文档按后端路由整理当前 API。所有接口由 `backend/app/main.py` 注册。

## 健康检查

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | API 健康检查 |

## 数据库

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/database/status` | 查看数据库、数据湖和运行环境状态 |
| GET | `/api/database/integration-overview` | 查看数据库集成总览、覆盖和水位线 |
| GET | `/api/database/lineage` | 查询入库批次和数据血缘 |

## 数据质量

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/data-quality/overview` | 质量状态总览 |
| GET | `/api/data-quality/reports` | 分页查询质量报告 |
| GET | `/api/data-quality/check-runs` | 查看最近质量检查运行 |
| POST | `/api/data-quality/check` | 执行数据质量检查 |

## 数据源

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/data-sources` | 列出已注册数据源 |
| PATCH | `/api/data-sources/{code}` | 修改启用状态或优先级 |
| POST | `/api/data-sources/{code}/health-check` | 执行轻量健康检查 |
| POST | `/api/data-sources/{code}/smoke-test` | 执行真实小样本取样 |

## 数据集

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/datasets` | 分页查询数据集目录 |
| GET | `/api/datasets/{name}` | 查看单个数据集 |

## 行情数据

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/market-data/daily-bars` | 分页查询日线行情 |
| GET | `/api/market-data/daily-bars?symbol={symbol}` | 按股票查询日线行情 |
| POST | `/api/market-data/daily-bars/sync` | 创建单股日线同步任务 |
| POST | `/api/market-data/daily-bars/market-repair/preview` | 预览市场级日线缺口补齐计划 |
| POST | `/api/market-data/daily-bars/market-repair` | 创建市场级日线缺口补齐任务 |

## 研究数据

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/research-data/bars` | 通过 `BarReader` 契约读取已治理日线，供后续研究、回测和 AI 消费 |

## 研究工作台

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/market/quote` | 查询实时股票行情 |
| GET | `/api/market/index` | 查询主要指数行情 |
| GET | `/api/market/kline` | 查询研究页 K 线 |
| GET | `/api/market/news` | 查询已入库新闻 |
| GET | `/api/market/search` | 搜索股票 |
| GET | `/api/market/sectors` | 查询板块排行 |
| GET | `/api/watchlist` | 查询默认自选股 |
| POST | `/api/watchlist/items` | 添加自选股 |
| DELETE | `/api/watchlist/items/{symbol}` | 删除自选股 |
| PUT | `/api/watchlist/items/reorder` | 调整自选股顺序 |

## 股票

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/stocks` | 分页查询股票池 |
| GET | `/api/stocks/{symbol}` | 查看股票基础信息 |
| GET | `/api/stocks/{symbol}/daily-coverage` | 查看单股日线覆盖 |
| GET | `/api/stocks/{symbol}/daily-quality` | 查看单股日线质量 |
| GET | `/api/stocks/{symbol}/daily-ingest-batches` | 查看单股最近日线入库批次 |
| POST | `/api/stocks/sync` | 创建股票池同步任务 |

## 同步任务

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/sync-tasks` | 分页查询同步任务 |
| GET | `/api/sync-tasks/schedules` | 查看定时同步配置 |
| GET | `/api/sync-tasks/runner-status` | 查看 worker 可执行任务和下一个 pending 任务 |
| PATCH | `/api/sync-tasks/schedules/{code}` | 修改定时同步配置 |
| POST | `/api/sync-tasks/schedules/{code}/trigger` | 手动触发定时配置对应任务 |
| GET | `/api/sync-tasks/{task_id}` | 查看任务详情 |
| GET | `/api/sync-tasks/{task_id}/logs` | 查看任务日志 |
| GET | `/api/sync-tasks/{task_id}/ingest-batches` | 查看任务入库批次 |

## 交易日历

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/trading-calendars` | 分页查询交易日历 |
| POST | `/api/trading-calendars/sync` | 创建交易日历同步任务 |

## API 约束

- 分页接口必须使用服务端分页。
- 日线查询必须限制返回行数。
- 同步类 API 只创建任务，不在请求内执行长任务。
- `daily_bars` 必须带 `symbol`。
- 市场补齐必须走 `daily_bars_market_repair`。
- 数据管线操作统一走 `market-data` / `sync-tasks` 正式任务链路，不注册脚本型 `/api/data-pipeline` 旁路。
- 研究、回测和 AI 读取日线数据时优先走 `research-data` 契约，不直接读取 provider、数据库表或 Parquet 物理路径。
