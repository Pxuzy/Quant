# Quant 项目总览

## 一句话定位

Quant 是一个本地优先的个人股票研究工作台，用可信的数据管理能力支撑股票、行情和新闻分析。

它不是大型数据湖平台，也不是一开始就追求完整量化交易系统。当前阶段先让 A 股股票池、日线、交易日历、数据源、同步任务、批次、质量和血缘跑成闭环，再把这些能力组织成更好用的股票研究入口。

## 当前产品目标

当前目标分成两层。

| 层级 | 目标 |
| --- | --- |
| 股票研究台 | 让用户每天能看关注股票、行情数值、新闻事件和单股详情 |
| 数据可信后台 | 让用户知道数据从哪里来、是否新鲜、缺什么、怎么补、能否追溯 |

数据库管理不是最终产品本身，而是研究台可信度的后台。后续页面设计和功能优先级都按这个口径收敛。

## 当前数据闭环

第一阶段优先打通真实数据闭环：

```text
AKShare / BaoStock / AData / Tushare / Stock SDK
  -> provider adapter
  -> normalize
  -> schema_validate
  -> ingest_batches
  -> metadata database / Parquet lake
  -> DuckDB query
  -> FastAPI
  -> React workbench
```

这个闭环回答四个问题：

| 问题 | 当前能力 |
| --- | --- |
| 数据从哪里来 | provider metadata、capabilities、health、sample、requested source 和实际 source |
| 数据是否新鲜 | latest data date、交易日历覆盖、最近半年日线覆盖 |
| 数据缺什么 | row count、coverage、missing symbol-days、quality issue |
| 数据怎么修 | 同步任务、市场级日线补齐、批次、日志和失败原因 |

## 当前系统形态

| 层级 | 当前实现 |
| --- | --- |
| 前端 | React + Vite + TypeScript + Ant Design + ProComponents + TanStack Router + TanStack Query |
| API | FastAPI，按业务域暴露稳定接口 |
| 元数据存储 | SQLite 本地 fallback，PostgreSQL 是主路径目标 |
| 行情数据湖 | Parquet，路径由后端和数据层管理 |
| 查询引擎 | DuckDB 优先查询 Parquet，保留 PyArrow fallback |
| 同步执行 | 轻量 worker |
| 数据源 | AKShare、BaoStock、AData、Tushare、Stock SDK |

## 产品入口

当前前端主导航按两层理解：

| 层级 | 入口 | 作用 |
| --- | --- | --- |
| 股票研究台 | 总控台 | 展示研究入口、关键数据状态、最近任务和快捷操作 |
| 股票研究台 | 股票池 | A 股列表、搜索筛选、单股详情和日线数据 |
| 股票研究台 | 新闻汇总 | 当前是新闻能力入口，后续接入真实新闻和股票关联 |
| 股票研究台 | 数值数据 | 当前是数值数据入口，后续聚合常用行情和指标 |
| 数据可信后台 | 数据源管理 | 数据源启用状态、优先级、能力、健康检查、真实取样 |
| 数据可信后台 | 同步调度 | 手动同步、定时配置、任务记录、日志、入库批次 |
| 数据可信后台 | 数据库管理 | 数据库状态、数据湖状态、数据集、血缘、质量、水位线 |

历史路由如 `/data-system/market-data`、`/data-system/datasets`、`/data-system/trading-calendars`、`/data-system/data-quality` 会重定向或收敛到股票池和数据库管理。

## 第一阶段明确不做

- 不做移动端。
- 不做完整回测引擎。
- 不做实盘交易和券商适配。
- 不做完整因子平台。
- 不做插件市场。
- 不把 Redis、MongoDB、Celery 作为第一阶段必需依赖。
- 不做 tick、orderbook、实时行情流。
- 不把新闻系统做成通用爬虫平台。

## 后续演进方向

第一阶段完成后，后续模块只能消费统一 API、silver/gold 数据集或稳定读取接口，不能直接调用第三方数据源或拼接 Parquet 路径。

下一步产品演进优先考虑三个方向：

- 股票详情页成为研究主页面，聚合行情、新闻、质量和批次。
- 新闻数据进入正式数据闭环，能按股票关联和追溯。
- 数据管理页继续做清晰的可信后台，突出“哪里缺、怎么补、补到哪里”。
