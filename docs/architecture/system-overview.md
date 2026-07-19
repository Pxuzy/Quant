# 系统架构总览

## 总体结构

```text
React stock workbench
  -> FastAPI routers
  -> Services
  -> Repositories / Adapters
  -> SQLite or PostgreSQL metadata
  -> Parquet lake
  -> DuckDB query
```

当前仓库采用模块化单体结构。产品上分成“工作台层”和“控制面”，技术上仍共用同一套 FastAPI、元数据库、Parquet 数据湖和同步任务体系。

| 路径 | 职责 |
| --- | --- |
| `frontend` | 前端股票研究台和数据可信后台 |
| `backend/app` | FastAPI 服务、领域服务、仓储、数据源适配器 |
| `backend/worker` | 同步任务执行入口 |
| `scripts` | 本地运行和运维脚本 |
| `tests` | API、worker、数据源和数据质量测试 |
| `docs` | 项目文档 |

## 产品层和技术层的关系

| 产品层 | 主要页面 | 依赖的技术能力 |
| --- | --- | --- |
| 工作台层 | 总控台、股票池、股票详情、新闻汇总、数值数据 | 股票 API、日线 API、后续新闻 API、数据新鲜度摘要 |
| 控制面 | 数据源管理、同步调度、数据库管理 | provider registry、sync tasks、ingest batches、datasets、quality、lineage |

研究页面不直接读取 provider、数据库或 Parquet 路径。它们只消费 API 和稳定数据集。控制面负责解释数据从哪里来、是否完整、如何修复。

## 后端模块

| 模块 | 代码位置 | 职责 |
| --- | --- | --- |
| health | `backend/app/routers/health.py` | 健康检查 |
| market | `backend/app/routers/market.py` | 研究台实时行情、指数、板块、新闻和搜索 |
| database | `backend/app/routers/database.py` | 数据库状态、集成总览、血缘 |
| data_quality | `backend/app/routers/data_quality.py` | 质量总览、报告、检查运行 |
| data_sources | `backend/app/routers/data_sources.py` | 数据源管理、健康检查、真实取样 |
| datasets | `backend/app/routers/datasets.py` | 数据集目录 |
| market_data | `backend/app/routers/market_data.py` | 日线查询、日线同步、市场补齐 |
| stocks | `backend/app/routers/stocks.py` | 股票池、股票详情、股票同步 |
| research_data | `backend/app/routers/research_data.py` | 研究数据读取契约 |
| sync_tasks | `backend/app/routers/sync_tasks.py` | 同步任务、日志、批次、定时配置 |
| trading_calendars | `backend/app/routers/trading_calendars.py` | 交易日历查询和同步 |
| watchlist | `backend/app/routers/watchlist.py` | 默认自选股管理 |

后续新闻能力进入正式范围时，应新增独立 news 领域模块，并接入标准化、批次、质量和股票关联，不从前端直接拉取外部新闻。

## 前端模块

| 层级 | 代码位置 | 说明 |
| --- | --- | --- |
| app | `frontend/src/app` | Router、Provider、主题 |
| layout | `frontend/src/layouts` | 侧边栏、顶部栏、内容容器 |
| pages | `frontend/src/pages/data-system` | 页面级编排 |
| features | `frontend/src/features` | 业务域 API、类型、组件 |
| shared | `frontend/src/shared` | API client、通用组件、标签和格式化 |

前端路由使用 TanStack Router，页面使用 lazy import。查询状态使用 TanStack Query，服务端业务数据不放入 Zustand。

页面设计边界：

- 工作台层页面优先展示股票、行情、新闻、数据新鲜度和下一步研究动作。
- 控制面页面优先展示 provider、同步、质量、批次、血缘、缺口和修复动作。
- 不把底层 schema、批次、新闻、股票详情全部混在一个页面里。

## 同步任务流

```text
前端创建同步任务
  -> FastAPI 创建 sync_tasks 记录
  -> worker 领取任务或直接执行
  -> provider adapter 拉取外部数据
  -> raw/staging 保存原始 provider 响应
  -> normalize 标准化
  -> schema_validate 校验
  -> 写入 stocks / trading_calendars / Parquet
  -> 写入 ingest_batches
  -> 更新 datasets 和 data_quality
  -> 返回任务状态、日志和批次
```

支持任务类型：

| 任务类型 | 用途 |
| --- | --- |
| `stock_list` | 同步股票池 |
| `daily_bars` | 同步单股日线 |
| `daily_bars_market_repair` | 市场级日线缺口补齐 |
| `calendars` | 同步交易日历 |

日线补齐默认以最近半年为管理窗口。覆盖计算以本地交易日历最新日期为锚点，不凭空推断未知交易日。

脚本型全量拉取、合并和增量更新不作为前端可调用 API 暴露。需要长时间执行的数据操作必须先落到 `sync_tasks`，再由 worker 执行，并留下日志、入库批次、数据集和质量记录。

数据管线的长期目标按 Qlib 的思路收敛为三段：

```text
download/fetch raw
  -> raw/staging 可回放留痕
  -> normalize/schema_validate
  -> silver/gold/research datasets
  -> BarReader/DataPortal
```

当前正式采集会先保存带 SHA-256 的 raw artifact，再做标准化、校验和写入；`daily_bars_raw_replay` 从已登记的 `raw_artifacts` 离线重跑标准化，不重新请求 provider。历史旁路脚本已删除，所有持久化采集统一走正式任务链路。详情见 [ADR-001](../decisions/ADR-001-raw-artifacts-and-offline-replay.md)。

## 数据源架构

数据源通过 `AdapterRegistry` 注册。当前默认注册：

- `akshare`
- `baostock`
- `stock_sdk`

每个 adapter 需要声明能力、元数据、健康检查和标准化输出。正式同步使用 `source=auto` 时，系统按启用状态、能力和优先级选择真实 provider，并在批次中记录最终来源。

## 存储边界

| 存储 | 当前用途 |
| --- | --- |
| SQLite | 本地 fallback，默认 `sqlite:///./storage/quant.db` |
| PostgreSQL | 主路径目标，通过 `DATABASE_URL` 切换 |
| Parquet | 日线行情等大表数据 |
| DuckDB | 查询 Parquet 的执行引擎 |

前端、后续因子、回测、策略模块不得直接拼接 Parquet 路径或调用第三方 provider。数据集版本、manifest、snapshot 和回测输入的后续实现以 [Dataset Version、Manifest 与 Snapshot 规格](./dataset-version-snapshot-design.md) 为准。

## 研究、回测和 AI 边界

后续量化回测和 AI 能力属于数据基础之上的消费层，不是新的数据接入主链路。

推荐演进顺序：

```text
governed ingest
  -> datasets / silver-gold lake
  -> research data access layer
  -> factors / backtest / AI assistant / strategy
```

第一步已经落地最小 `BarReader` 契约：`/api/research-data/bars` 按市场、股票和时间范围读取已治理日线，并在 `contract.manifest` 返回 `daily_bars` 数据集的行数、最新数据日、质量状态、来源、更新时间和最新成功入库批次。后续可以扩展为 `DataPortal`，但调用方不应该知道 provider、数据库表名或 Parquet 物理路径。

AI 能力可以做四类事情：

- 总结股票、新闻、质量和同步状态。
- 解释数据缺口、来源、批次和质量报告。
- 生成研究问题、因子草案和回测配置。
- 调用受控工具执行查询或任务。

AI 不能绕开数据治理直接抓外部数据写入结果。需要持久化的数据仍必须经过 `normalize -> schema_validate -> ingest_batches -> quality`。

## 后续新闻数据边界

新闻能力进入正式建设时，建议保持和股票数据一致的治理口径：

```text
news provider
  -> normalize article
  -> stock linking
  -> ingest_batches
  -> news_articles / stock_news_links
  -> quality check
  -> API
  -> 总控台 / 新闻汇总 / 股票详情
```

新闻不是通用爬虫平台。它只服务股票研究场景，先覆盖标题、来源、发布时间、链接、摘要和股票关联。
