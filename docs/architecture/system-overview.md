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

当前仓库采用模块化单体结构。产品上分成“股票研究台”和“数据可信后台”，技术上仍共用同一套 FastAPI、元数据库、Parquet 数据湖和同步任务体系。

| 路径 | 职责 |
| --- | --- |
| `apps/web` | 前端股票研究台和数据可信后台 |
| `apps/api` | FastAPI 服务、领域服务、仓储、数据源适配器 |
| `apps/worker` | 同步任务执行入口 |
| `quant` | 本地运行脚本、环境示例、依赖和 Docker Compose |
| `tests` | API、worker、数据源和数据质量测试 |
| `docs` | 项目文档 |

## 产品层和技术层的关系

| 产品层 | 主要页面 | 依赖的技术能力 |
| --- | --- | --- |
| 股票研究台 | 总控台、股票池、股票详情、新闻汇总、数值数据 | 股票 API、日线 API、后续新闻 API、数据新鲜度摘要 |
| 数据可信后台 | 数据源管理、同步调度、数据库管理 | provider registry、sync tasks、ingest batches、datasets、quality、lineage |

研究页面不直接读取 provider、数据库或 Parquet 路径。它们只消费 API 和稳定数据集。数据可信后台负责解释数据从哪里来、是否完整、如何修复。

## 后端模块

| 模块 | 代码位置 | 职责 |
| --- | --- | --- |
| health | `apps/api/routers/health.py` | 健康检查 |
| database | `apps/api/routers/database.py` | 数据库状态、集成总览、血缘 |
| data_quality | `apps/api/routers/data_quality.py` | 质量总览、报告、检查运行 |
| data_sources | `apps/api/routers/data_sources.py` | 数据源管理、健康检查、真实取样 |
| datasets | `apps/api/routers/datasets.py` | 数据集目录 |
| market_data | `apps/api/routers/market_data.py` | 日线查询、日线同步、市场补齐 |
| stocks | `apps/api/routers/stocks.py` | 股票池、股票详情、股票同步 |
| sync_tasks | `apps/api/routers/sync_tasks.py` | 同步任务、日志、批次、定时配置 |
| trading_calendars | `apps/api/routers/trading_calendars.py` | 交易日历查询和同步 |

后续新闻能力进入正式范围时，应新增独立 news 领域模块，并接入标准化、批次、质量和股票关联，不从前端直接拉取外部新闻。

## 前端模块

| 层级 | 代码位置 | 说明 |
| --- | --- | --- |
| app | `apps/web/src/app` | Router、Provider、主题 |
| layout | `apps/web/src/layouts` | 侧边栏、顶部栏、内容容器 |
| pages | `apps/web/src/pages/data-system` | 页面级编排 |
| features | `apps/web/src/features` | 业务域 API、类型、组件 |
| shared | `apps/web/src/shared` | API client、通用组件、标签和格式化 |

前端路由使用 TanStack Router，页面使用 lazy import。查询状态使用 TanStack Query，服务端业务数据不放入 Zustand。

页面设计边界：

- 股票研究台页面优先展示股票、行情、新闻、数据新鲜度和下一步研究动作。
- 数据可信后台页面优先展示 provider、同步、质量、批次、血缘、缺口和修复动作。
- 不把底层 schema、批次、新闻、股票详情全部混在一个页面里。

## 同步任务流

```text
前端创建同步任务
  -> FastAPI 创建 sync_tasks 记录
  -> worker 领取任务或直接执行
  -> provider adapter 拉取外部数据
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

## 数据源架构

数据源通过 `AdapterRegistry` 注册。当前默认注册：

- `akshare`
- `baostock`
- `adata`
- `tushare`
- `stock_sdk`

每个 adapter 需要声明能力、元数据、健康检查和标准化输出。正式同步使用 `source=auto` 时，系统按启用状态、能力和优先级选择真实 provider，并在批次中记录最终来源。

## 存储边界

| 存储 | 当前用途 |
| --- | --- |
| SQLite | 本地 fallback，默认 `sqlite:///./storage/quant.db` |
| PostgreSQL | 主路径目标，通过 `DATABASE_URL` 切换 |
| Parquet | 日线行情等大表数据 |
| DuckDB | 查询 Parquet 的执行引擎 |

前端、后续因子、回测、策略模块不得直接拼接 Parquet 路径或调用第三方 provider。

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
