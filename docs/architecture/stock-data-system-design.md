# Stock Data System Architecture Design

日期：2026-06-05

> 说明：本文是历史技术架构参考。当前产品定位与首读路径请以 [个人股票研究工作台产品方向](../product/personal-stock-workbench.md) 和 [项目总览](../overview/project-overview.md) 为准。若与这些新文档冲突，以新文档为准。

## 1. 目标

当前产品目标以 [股票数据库工作台项目文档](./stock-database-workbench.md) 为准，尤其以其中的“项目目标基线”和“项目总架构目标（第一阶段基准）”作为第一阶段验收口径。本文件是股票数据库工作台的技术实现架构，不重新定义产品目标；五个主入口和第一阶段数据闭环以工作台文档为唯一产品基线。本设计文档负责展开技术架构、模块边界、数据流和工程约束；如果后续细节与工作台目标冲突，优先按工作台目标调整。

本项目先从股票数据管理系统开始建设，后续再扩展到因子研究、策略生成、回测、组合管理、风控和交易执行。第一阶段的目标不是一次性做完整量化平台，而是做一个稳定、可扩展、边界清晰的数据底座。

核心目标：

- 管理 A 股股票基础资料、交易日历、行情数据和数据质量。
- 支持多个数据源，优先使用免费或低门槛数据源，Tushare 等带凭证的数据源作为可选增强。
- 支持日线行情作为第一批核心数据，后续可扩展分钟线、财务数据、公告、行业、指数、资金流和因子数据。
- 让策略、回测、研究模块以后只依赖统一数据服务，不直接依赖某个数据源、数据库表或文件路径。
- 用模块化单体起步，避免过早微服务化，同时保留未来拆服务的边界。

非目标：

- 第一阶段不做实盘交易。
- 第一阶段不做完整回测引擎。
- 第一阶段不把所有数据源能力一次性做齐。
- 第一阶段不追求复杂权限、多租户和企业级部署。
- 第一阶段只做桌面管理后台，不建设移动端页面或移动端工作流。

## 2. 推荐架构

采用模块化单体 Monorepo：

```text
Quant/
  apps/
    api/                         # FastAPI API 服务
    web/                         # React + Vite + Ant Design 管理后台
    worker/                      # 数据同步、清洗、质量检测任务
  packages/
    domain/                      # 领域模型、枚举、接口契约
    data-adapters/               # 数据源插件
    data-engine/                 # DuckDB/Parquet 查询与写入
    shared/                      # 日志、配置、错误码、工具函数
  storage/
    lake/                        # Parquet 数据湖
      raw/
      bronze/
      silver/
      gold/
    postgres/
      migrations/
      seeds/
  configs/
    data_sources.yaml
    app.yaml
  docs/
    architecture/
```

技术选型：

- 后端 API：FastAPI
- 元数据库：PostgreSQL
- 行情数据湖：Parquet
- 本地分析查询：DuckDB
- 任务执行：独立 worker 进程，第一阶段可用 APScheduler 或轻量任务队列，后续再升级 Celery/RQ。
- 前端：React + Vite + TypeScript + Ant Design + ProComponents
- 前端路由：TanStack Router
- 前端请求和缓存：TanStack Query
- 前端状态：Zustand，仅保存布局、主题、轻量 UI 状态
- 图表：ECharts

说明：SQL 是访问关系型元数据库和 DuckDB 查询引擎时使用的查询语言或接口能力，不代表另一个独立存储系统。PostgreSQL/SQLite 是元数据库连接，Parquet 是行情大表文件存储，DuckDB 是读取和分析 Parquet 的查询引擎。

## 3. 架构原则

### 3.1 模块边界优先

任何模块都不能绕过服务契约访问另一个模块的内部实现。尤其禁止：

- 前端直接理解数据源字段。
- 策略模块直接读取 Parquet 文件路径。
- 回测模块直接调用 AkShare、BaoStock、Tushare 等数据源适配器。
- 数据源配置混入通用系统配置。
- 任务调度代码里写大量业务清洗逻辑。

每个模块应该回答三个问题：

- 它负责什么？
- 它暴露什么接口？
- 它依赖什么？

如果一个模块无法简单回答这三个问题，就说明边界不清。

### 3.2 数据源插件化

每个数据源都是插件，不是散落在业务代码里的 if/else。

数据源插件至少提供：

```text
capabilities()      # 声明支持股票列表、日线、分钟线、财务等哪些能力
fetch()             # 拉取原始数据
normalize()         # 转成系统标准结构
health_check()      # 检查可用性、限流、凭证状态
```

数据源插件不负责：

- 决定数据是否入库。
- 写 PostgreSQL。
- 写 Parquet。
- 计算因子。
- 判断策略信号。

### 3.3 数据分层

数据湖采用四层结构：

```text
raw       # 原始响应，尽量保留来源格式，便于追溯
bronze    # 字段初步标准化，仍可能有缺失和重复
silver    # 经过清洗、去重、校验后的主数据
gold      # 给研究、因子、策略、回测直接使用的数据集
```

第一阶段可以只实现 `silver` 主路径，但目录和接口要提前按分层设计，避免后续迁移成本过高。

### 3.4 元数据和大表分离

PostgreSQL 负责：

- 股票基础资料
- 数据源配置
- 同步任务
- 数据质量报告
- 数据目录
- 数据集版本
- 用户可见配置

Parquet 负责：

- 日线行情
- 分钟线行情
- 复权行情
- 因子矩阵
- 大规模回测输入

DuckDB 负责：

- 本地快速查询 Parquet
- 数据预览
- 数据质量扫描
- 研究型聚合查询

### 3.5 从模块化单体起步

第一阶段不要拆微服务。推荐单仓库、多应用、多包：

- `apps/api` 提供 HTTP API。
- `apps/worker` 运行数据任务。
- `apps/web` 提供管理界面。
- `packages/*` 存放可复用核心逻辑。

未来如果需要拆服务，优先拆出：

1. 数据同步服务
2. 数据查询服务
3. 回测服务
4. 交易执行服务

拆服务的前提是服务契约已经稳定，而不是因为目录看起来复杂。

## 4. 核心能力

第一阶段产品对外只保留五个主功能区，详细产品目标以 [股票数据库工作台项目文档](./stock-database-workbench.md) 为准：

```text
总控台
股票池
数据源管理
同步调度
数据库管理
```

这里的 `stocks`、`market_data`、`data_quality`、`datasets` 等不是新的前端主导航，而是后端和数据层的领域能力。前端只把它们组合进五个主功能区，避免页面数量失控，也避免后端模块反向决定产品菜单。

### 4.1 股票基础资料模块 stocks

职责：

- 管理股票代码、名称、市场、交易所、上市状态、行业、上市日期、退市日期。
- 提供分页、搜索、筛选、详情 API。
- 维护股票代码标准化规则。

不负责：

- 拉取具体行情。
- 计算涨跌幅。
- 执行同步任务。

建议 PostgreSQL 表：

```text
stocks
  id
  symbol                 # 系统内部代码，如 600519
  exchange               # SSE / SZSE / BSE
  market                 # A_SHARE / HK / US
  name
  status                 # LISTED / DELISTED / SUSPENDED
  industry
  listing_date
  delisting_date
  source
  created_at
  updated_at
```

### 4.2 交易日历模块 calendars

职责：

- 管理每个市场的交易日、休市日。
- 为行情完整性检查和任务增量同步提供日期范围。

建议 PostgreSQL 表：

```text
trading_calendars
  id
  market
  trade_date
  is_open
  source
  updated_at
```

### 4.3 行情数据模块 market_data

职责：

- 定义日线、分钟线、复权行情的数据结构。
- 提供统一查询 API。
- 屏蔽底层 Parquet/DuckDB 细节。

不负责：

- 直接调用数据源。
- 决定同步策略。

建议 Parquet 分区：

```text
storage/lake/silver/daily_bars/
  market=A_SHARE/
    trade_date=2026-06-05/
      part-000.parquet

storage/lake/silver/minute_bars/
  market=A_SHARE/
    freq=1m/
      trade_date=2026-06-05/
        part-000.parquet
```

日线标准字段：

```text
symbol
exchange
market
trade_date
open
high
low
close
pre_close
volume
amount
adjust_factor
adjust_type
source
ingested_at
```

### 4.4 数据源模块 data_sources

职责：

- 管理数据源启用状态、优先级、凭证、能力声明和健康状态。
- 提供统一适配器接口。
- 支持 AkShare、BaoStock、AData、Tushare、Stock SDK 五类第一版来源；其中 Tushare 为 Token 增强源，Stock SDK 为 Node 可选包增强源。
- 第一版产品 registry 只暴露 `akshare`、`baostock`、`adata`、`tushare`、`stock_sdk`；其他演示型、测试型或未明确纳入第一版的 provider 不注册为产品数据源。

建议 PostgreSQL 表：

```text
data_sources
  id
  code                   # akshare / baostock / adata / tushare / stock_sdk
  name
  enabled
  priority
  requires_token
  config_json
  health_status
  last_checked_at
  created_at
  updated_at
```

配置规则：

- 数据源配置只属于数据系统。
- 不写入通用系统设置。
- 凭证字段加密或至少从环境变量读取。
- 每个数据源必须声明能力，不能默认假设支持所有数据类型。

#### 4.4.1 参考开源项目后的数据源接入原则

本项目的数据源管理参考以下成熟开源项目的共同模式，但不直接照搬其目录结构：

- AkShare：把大量公开数据入口封装成独立函数，并尽量返回表格化结果；本项目借鉴其“函数级数据入口 + adapter normalize”的模式。
- vn.py：使用 `BaseDatafeed` 风格的统一数据源接口，并通过配置选择具体 provider；本项目借鉴其“统一接口 + 可替换 provider”的模式。
- Qlib：强调数据 provider 和本地标准化数据层分离，研究/回测读取统一格式；本项目借鉴其“先标准化入库，再给上层模块使用”的边界。
- OpenBB：使用 provider、标准模型和 fetcher 管线来屏蔽不同来源差异；本项目借鉴其“provider metadata + capability + 标准输出”的模式。
- Zipline：使用 data bundle/ingest 思路，把外部数据先写成可重复加载的本地数据包，再供回测读取；本项目借鉴其“先入库形成版本化快照，再给上层使用”的模式。

落到本项目的规则：

- 每个数据源 adapter 必须声明 `capabilities`，例如 `stock_list`、`daily_bars`、`calendars`。
- 每个数据源 adapter 必须声明 `provider_metadata`，包括接入类型、文档链接、认证方式、稳定性、限流/安装说明。
- 业务同步任务不直接写死某个 provider，而是通过 registry 和数据源表做选择。
- 手动同步允许指定具体来源；默认同步使用 `source=auto`，按启用状态、能力和优先级逐个尝试。
- 自动模式下每次 provider 尝试都要写任务日志，失败后降级到下一个来源，最终记录实际写入数据集的 provider。
- 禁用的数据源不参与自动选择，健康检查失败的数据源会被标记为 `unhealthy` 或 `unavailable`。

#### 4.4.2 数据源接入工程规则

参考 Qlib、Zipline、vn.py、OpenBB 后，本项目不把数据源接入做成“页面直接调第三方接口”，而是拆成下面的稳定链路：

```text
外部数据源
  -> adapter.fetch 原始拉取
  -> adapter.normalize 标准化
  -> schema_validate 契约校验
  -> ingest_batch 形成同步批次
  -> write_silver 写入主数据
  -> quality_check 质量检查
  -> catalog/lineage 更新目录和血缘
  -> API 给前端、研究、回测使用
```

必须遵守：

- adapter 输出必须经过 schema 校验，不能只靠字段名约定。日线至少校验 `symbol`、`market`、`exchange`、`trade_date`、OHLCV、`amount`、`source`、`ingested_at`。
- 每个字段要明确单位和口径，例如成交量是股还是手，成交额是元还是千元，价格是否复权，日期是否交易日。
- 同一数据类型要有统一内部代码规则，外部的 `000001.SZ`、`sh.600000`、`600000` 都必须转成系统内部的 `symbol + exchange + market`。
- 同一任务重复执行必须幂等。对于 `stocks` 使用 upsert；对于 `daily_bars` 使用 `(market, symbol, trade_date, adjust_type)` 去重或覆盖；不能因为 provider fallback 产生混源重复记录。
- 每次同步都要有 `ingest_batch_id` 或等价批次标识，记录实际 provider、请求范围、开始/结束时间、schema 版本、normalize 版本、写入行数和质量结果。
- `source=auto` 只决定本次优先尝试顺序，不改变最终数据契约。最终数据必须记录实际写入来源，而不是只记录 `auto`。
- raw 层可以先做轻量保留，不强制保存所有原始响应；但重要失败、取样结果和字段映射差异必须可追踪。
- 上层研究、回测、因子模块只能读 API、silver/gold 数据集或后续稳定数据服务，不能直接调用第三方数据源。

第一阶段不照搬的内容：

- 不照搬 OpenBB 的完整 provider/fetcher/standard-model 插件生态和插件市场。第一版只做 registry、能力声明、五个明确 provider 和统一输出。
- 不照搬 Qlib 的完整研究数据格式、表达式引擎和 PIT 数据库。第一版只借鉴本地标准化数据层和 provider_uri 思路。
- 不照搬 Zipline 的完整 bundle 目录和回测资产生命周期系统。第一版只借鉴可重复 ingest、数据快照和失败不写半成品的原则。
- 不照搬 vn.py 的交易网关、事件引擎和实时推送。第一版只借鉴统一 datafeed 接口和可替换数据服务。

#### 4.4.3 借鉴成熟量化项目后的数据工程原则

参考 Qlib、Zipline、LEAN、OpenBB、vn.py、backtrader 后，本项目只吸收对“股票数据库工作台”有直接价值的数据工程原则，不把第一阶段做成完整量化研究、回测或实盘平台。

成熟项目里值得借鉴的共同点：

- Qlib：强调先把外部数据转换为本地标准数据层，再通过 Data Loader、Data Handler、Dataset、Cache 提供给研究和模型使用。对本项目的启发是：上层模块不能直接依赖具体 provider，而应该依赖统一数据服务和 silver/gold 数据集。
- Zipline：使用 data bundle/ingest，把价格、复权调整、资产元数据、交易日历写入可重复加载的本地格式，失败时不写半成品。对本项目的启发是：每次同步都要形成批次、版本和可回放快照。
- LEAN：用稳定的 Symbol/SecurityIdentifier 识别资产，并把复权模式、拆分、分红、改名、退市等公司行动作为独立数据语义处理。对本项目的启发是：股票代码字符串不是长期唯一身份，复权和公司行动不能混在普通 OHLCV 字段里。
- OpenBB：用标准 QueryParams/Data 模型、provider metadata、fetcher 管线统一不同数据源的参数和返回结构。对本项目的启发是：所有 provider 都必须有能力声明、字段契约、类型校验和标准输出。
- vn.py：用 BaseDatafeed 风格接口隔离具体数据服务。对本项目的启发是：替换 provider 不应影响同步任务、数据质量和前端页面。
- backtrader：策略消费 data feed，而不是直接消费某个下载函数；并支持不同周期数据的 resample/replay。对本项目的启发是：后续回测读取的是稳定行情读取接口，不直接读第三方接口或 Parquet 路径。

落到本项目的标准做法：

1. **数据源只是入口，本地标准数据层是核心。** 第三方接口只负责拉取，正式业务只认系统标准 schema、ingest batch、dataset catalog 和质量结果。
2. **资产身份要独立于代码字符串。** 第一阶段继续使用 `symbol + exchange + market`，但模型和文档预留 `instrument_id/security_id`、代码历史、上市/退市有效区间，防止退市、改名、转板、代码复用造成历史数据歧义。
3. **复权口径必须显式。** 日线数据必须带 `adjust_type`，第一阶段先支持不复权/前复权等查询口径；后续把复权因子、分红、送转、拆并股、改名和退市事件独立建模，查询时再生成对应口径。
4. **同步结果必须可重跑、可追溯。** 每次正式写入都要记录 `ingest_batch_id`、实际 provider、请求 provider、数据类型、范围、schema 版本、normalize 版本、写入行数、质量状态和错误。
5. **数据集要有版本和快照。** 可供研究/回测使用的数据集要逐步增加 `dataset_version`、manifest、分区清单、schema 摘要和回滚策略。第一阶段可以用 `ingest_batches + datasets` 轻量实现，不照搬完整 bundle 目录。
6. **增量同步要有水位线。** 为 `provider + data_type + market/symbol` 维护最近成功日期、最近检查时间、修复窗口和失败原因，避免每天全量重拉，也方便失败后续跑。
7. **多源整合要对账，不要静默拼接。** `source=auto` 可以按优先级 fallback，但最终写入要记录实际来源；不同 provider 对同一股票同一交易日给出不一致数据时，要生成差异记录和质量告警，不能无痕混成一个结果。
8. **Schema 演进要可控。** 新增字段、删除字段、字段类型变化、nullable 变化、价格/成交量精度变化都要提升 schema 版本；adapter 要保留小样本 golden sample 测试，避免第三方字段变动悄悄污染主数据。
9. **交易日历要表达 session 语义。** 交易日历不只是日期列表，还要逐步表达市场时区、开收盘时间、节假日调整、半日市、停牌/临停和收盘后数据可用时间。第一阶段先覆盖 A 股开闭市日期。
10. **查询侧要有 BarReader/DataPortal 抽象。** 后续因子、指标、回测应通过稳定读取接口按市场、股票集合、日期范围、字段列投影批量读取，避免 N+1 查询和直接拼 Parquet 路径。
11. **数据可观测性要产品化。** 数据库管理页除了质量报告，还要逐步展示 freshness、coverage、ingest latency、provider failure rate、fallback 次数、最新数据日期和异常趋势。

第一阶段采纳：

- provider registry、capabilities、provider metadata、health check、smoke test。
- adapter.fetch -> normalize -> schema_validate -> ingest_batch -> write_silver -> quality_check -> catalog 的稳定链路。
- `stocks` upsert、`daily_bars` 按 `(market, symbol, trade_date, adjust_type)` 幂等写入。
- `ingest_batches` 记录真实来源、请求来源、schema/normalize 版本、写入数量和错误。
- 数据源自动选择、手动指定、失败降级和任务日志。
- 数据质量基础检查、数据目录、数据新鲜度和同步批次展示。

第一阶段只预留、不强做：

- 完整 `instrument_id/security_id` 映射表、代码历史和资产生命周期引擎。
- 完整公司行动数据库、复权因子全历史和多复权模式重算。
- Point-in-time 财务数据库、公告可得时间、新闻可得时间和历史修订版本。
- 完整 Qlib 因子表达式引擎、Zipline bundle 管理、LEAN 实时订阅、OpenBB 插件市场、backtrader 回测运行时。
- tick/orderbook/实时流、Kafka/Airflow/Delta/Iceberg 等重型数据平台能力。

### 4.5 同步任务模块 sync_tasks

职责：

- 创建、执行、重试、取消数据同步任务。
- 记录任务状态、范围、来源、耗时、错误和影响记录数。
- 支持手动同步和定时同步。

建议 PostgreSQL 表：

```text
sync_tasks
  id
  task_type              # stock_list / daily_bars / daily_bars_market_repair / calendars
  source
  market
  symbol
  start_date
  end_date
  status                 # pending / running / success / failed / canceled
  progress
  records_read
  records_written
  error_message
  started_at
  finished_at
  created_at
```

任务执行原则：

- API 只创建任务，不执行长时间任务。
- worker 负责执行任务。
- 任务必须可重试。
- 每个任务都必须写入可读日志。
- 任务结果必须能回溯到数据源和时间范围。
- `daily_bars` 是单股日线同步任务，必须有 `symbol`，用于股票详情和单股补数。
- `daily_bars_market_repair` 是市场级日线缺口补齐任务，不接收 `symbol`，由后端基于股票池、交易日历和已有日线数据计算缺口。
- 市场级补齐第一阶段只做 A 股、指定日期范围和受控阈值，不做无限全市场全历史重拉。
- `source=auto` 只能选择本次实际 provider，最终任务日志和入库批次必须记录真实写入来源。

### 4.6 数据质量模块 data_quality

职责：

- 检查缺失交易日、重复记录、价格异常、成交量异常和字段完整率。
- 生成质量报告供前端展示。
- 为后续策略和回测提供可信数据标识。

建议 PostgreSQL 表：

```text
data_quality_reports
  id
  dataset
  market
  symbol
  date_range_start
  date_range_end
  completeness_ratio
  duplicate_count
  missing_count
  anomaly_count
  status                 # good / warning / degraded / failed
  details_json
  created_at
```

第一阶段质量规则：

- 日线数据不能有重复的 `(market, symbol, trade_date, adjust_type)`。
- 交易日历开市日期应该有行情。
- OHLC 价格必须大于等于 0。
- `high >= low`。
- `high >= open/close`，`low <= open/close`。
- 成交量和成交额不能为负。

### 4.7 数据目录模块 catalog

职责：

- 展示系统已有数据集、字段、来源、更新时间、记录数、质量状态。
- 给后续研究和策略模块提供可发现的数据入口。

建议 PostgreSQL 表：

```text
datasets
  id
  name
  layer                  # raw / bronze / silver / gold
  storage_type           # postgres / parquet
  path
  schema_json
  primary_keys_json
  partition_keys_json
  source
  dataset_version
  manifest_json
  lineage_json
  row_count
  latest_data_date
  quality_status
  updated_at
```

## 5. API 设计

第一阶段 API 应该保持业务语义清晰：

```text
GET    /api/stocks
GET    /api/stocks/{symbol}
POST   /api/stocks/sync

GET    /api/market-data/daily-bars
GET    /api/market-data/daily-bars/{symbol}
POST   /api/market-data/daily-bars/sync
POST   /api/market-data/daily-bars/market-repair

GET    /api/data-sources
PATCH  /api/data-sources/{code}
POST   /api/data-sources/{code}/health-check
POST   /api/data-sources/{code}/smoke-test

GET    /api/sync-tasks
GET    /api/sync-tasks/{id}
POST   /api/sync-tasks/{id}/retry
POST   /api/sync-tasks/{id}/cancel

GET    /api/data-quality/overview
GET    /api/data-quality/reports
POST   /api/data-quality/check

GET    /api/datasets
GET    /api/datasets/{name}
```

API 规则：

- 前端只调用 API，不直接访问数据库或数据文件。
- API 响应使用统一错误结构。
- 分页接口必须是服务端分页。
- 大数据预览必须限制返回行数。
- 查询行情时必须要求市场、代码、日期范围或合理默认范围。
- 单股日线同步 API 必须要求 `symbol`；市场级缺口补齐使用独立 API 和任务类型，不能用空 `symbol` 代表全市场。

## 6. 前端架构和页面

前端采用 React + Vite + TypeScript + Ant Design + ProComponents。项目不直接使用完整 Ant Design Pro/Umi 模板作为强约束，而是采用 Ant Design Pro 的后台设计体系和 ProComponents 的高级表单/表格能力。这样可以兼顾开发效率、视觉质量和长期模块化。

推荐目录：

```text
apps/web/
  src/
    app/                         # 应用入口、全局 Provider、路由注册
    layouts/                     # 后台布局、侧边栏、顶部栏
    routes/                      # TanStack Router 路由定义
    pages/
      data-system/
        overview/                # 总控台
        stocks/
        data-sources/
        sync-tasks/
        database/
    features/
      stocks/                    # 股票业务组件、hooks、api adapter
      market-data/               # 行情领域能力，组合进股票详情和同步调度
      data-sources/
      sync-tasks/
      database/
      data-quality/              # 数据质量领域能力，组合进数据库管理和股票详情
      datasets/                  # 数据目录领域能力，组合进数据库管理
      trading-calendars/         # 交易日历领域能力，组合进数据库管理和同步调度
    shared/
      api/                       # API client、请求拦截、错误处理
      components/                # 跨业务复用组件
      constants/
      hooks/
      types/
      utils/
```

前端依赖规则：

- `pages/*` 只负责页面编排，不写复杂业务逻辑。
- `features/*` 按业务域组织组件、hooks 和 API 调用。
- `shared/*` 只能放跨业务通用能力，不能放股票、行情、数据源等具体业务逻辑。
- 页面数据统一通过 TanStack Query 获取，避免组件里手写分散的 loading/error/cache 逻辑。
- Zustand 只保存主题、侧边栏折叠、用户偏好等轻量 UI 状态，不保存服务端业务数据。
- 路由查询参数承载列表筛选条件，例如市场、状态、关键字、页码和日期范围，便于刷新后恢复页面。
- 大表必须使用服务端分页、虚拟滚动或受限预览，前端禁止一次性拉取全量行情数据。

设计基调：

- 管理后台优先信息密度、可扫描性和稳定感。
- 采用 Ant Design Pro light 风格作为默认视觉方向。
- 用表格、筛选器、状态标签、抽屉详情、任务时间线、质量图表作为主要界面语言。
- 不做营销式 Hero，不做大面积装饰渐变，不牺牲数据可读性换取视觉效果。
- 页面视觉可以精致，但布局必须服务于高频查询、筛选、比较和排错。

第一阶段主功能区：

```text
总控台
  - 股票数量
  - 最新交易日
  - 行情覆盖率
  - 数据源健康状态
  - 最近同步记录
  - 数据质量告警
  - 常用入口：股票池、数据源管理、数据库管理、同步调度

股票池
  - A 股全量股票池分页列表
  - 搜索
  - 市场/状态/行业筛选
  - 股票基础资料
  - 单股详情入口
  - 日线数据和基础 K 线图
  - 常用指标
  - 新闻占位，后续补充

数据源管理
  - 启用/禁用
  - 优先级
  - 健康检查
  - 真实取样
  - 凭证状态
  - 能力声明

同步调度
  - 手动同步
  - 定时同步计划
  - 同步记录列表
  - 失败重试
  - 日志查看

数据库管理
  - 元数据库状态
  - 数据湖容量
  - 存放内容
  - 最新数据时间
  - 交易日历覆盖
  - 数据质量风险
```

收敛规则：

```text
日线行情、交易日历、数据质量、数据目录不作为主导航入口。
日线行情进入股票池的单股详情和行情明细能力。
交易日历、数据质量、数据目录收敛到数据库管理。
旧的明细页面可以作为隐藏调试/钻取路由存在，但不进入主导航。
```

后续待补子能力：

```text
股票详情
  - 基本信息
  - 日线图表和原始日线表
  - MA5 / MA10 / MA20 等基础指标
  - 新闻占位

数据库管理明细
  - 覆盖率
  - 缺失统计
  - 异常记录
  - 质量报告
  - 数据集列表
  - schema
  - 分区字段
  - 最新日期
```

UI 规则：

- 管理后台优先信息密度和可扫描性，不做营销式大 Hero。
- 页面以表格、筛选器、状态卡片、任务日志、图表为主。
- 控件使用专业后台习惯：分页表格、抽屉详情、模态确认、标签状态、进度条、时间线日志。
- 数据源配置只出现在数据系统页面。

## 7. 数据流

股票列表同步：

```text
用户点击同步
  -> API 创建 sync_task
  -> worker 领取任务
  -> data_source adapter 拉取原始股票列表
  -> normalize 标准化字段
  -> 写入 stocks
  -> 更新 datasets/catalog
  -> 生成质量报告
  -> 更新任务状态
```

单股日线行情同步：

```text
用户或股票详情页创建 daily_bars 任务
  -> API 校验 market / symbol / date range
  -> worker 读取单股任务范围
  -> 按指定来源或 auto 优先级拉取该股票行情
  -> normalize 为 daily_bars schema
  -> 写入 Parquet silver 层
  -> DuckDB 扫描校验
  -> 写入数据质量报告
  -> 更新数据目录
  -> 更新任务状态
```

市场级日线缺口补齐：

```text
数据库管理发现水位线或覆盖率缺口
  -> 用户进入同步调度创建 daily_bars_market_repair 任务
  -> API 校验 market / date range / 安全阈值
  -> worker 读取股票池和交易日历
  -> 对比已有 daily_bars，生成缺口股票和交易日计划
  -> 按股票顺序拉取缺失范围
  -> 每只股票形成可追溯 ingest batch
  -> 写入 Parquet silver 层并更新 catalog / quality / watermarks
  -> 任务汇总 records_read / records_written / 失败原因
```

第一阶段市场补齐不做并发调度、跨 provider 混写、全历史无阈值重拉和复杂子任务树；先保证补齐范围清楚、来源清楚、批次清楚、失败位置清楚。

行情预览：

```text
前端发起查询
  -> API 校验 symbol/date range
  -> market_data service 调用 data-engine
  -> DuckDB 查询 Parquet
  -> 返回分页或限制后的结果
```

## 8. 后续模块接入规则

后续模块必须依赖数据系统公开接口：

```text
因子模块
  -> 读取 market_data service
  -> 写 gold/factors 数据集

回测模块
  -> 读取 gold 或 silver 数据集
  -> 不直接调用数据源

策略模块
  -> 读取因子、行情、组合和回测结果
  -> 不直接读 Parquet 路径

交易模块
  -> 读取策略信号
  -> 通过 broker adapter 执行
  -> 不污染数据系统
```

这条规则是长期防止架构腐化的核心：数据系统是底座，不是所有业务逻辑的大杂烩。

## 9. MVP 范围

第一版只做闭环：

```text
1. 项目脚手架
2. FastAPI 基础服务
3. PostgreSQL 元数据模型
4. AkShare/BaoStock/Tushare 数据源插件框架
5. 股票列表同步
6. 日线行情同步到 Parquet
7. DuckDB 行情查询
8. 同步任务和任务日志
9. 数据质量基础检查
10. React + Vite + Ant Design/ProComponents 数据系统后台
```

第一版验收标准：

- 可以同步股票基础列表。
- 可以同步指定股票和日期范围的日线行情。
- 可以在前端分页查看股票列表。
- 可以在前端查询日线行情预览。
- 可以查看数据源健康状态。
- 可以查看同步任务状态和失败原因。
- 可以看到数据质量报告。
- 每个核心模块都有最小测试或可重复验证命令。

### 9.1 第一阶段实现状态 / 不适合点 / 下一步

当前实现状态以仓库当前代码为准，不把规划项视为已完成项。

已完成：

- 后端已落地 FastAPI 基础服务、健康检查、股票列表查询、股票列表同步任务创建、同步任务列表查询、同步任务详情和任务日志查询。
- 元数据模型已覆盖 `stocks`、`data_sources`、`sync_tasks`、`sync_task_logs`、`ingest_batches`、`datasets`，当前开发启动使用 SQLAlchemy + SQLite bootstrap fallback，`DATABASE_URL` 可覆盖。
- worker 已提供股票列表同步入口；默认使用 `source=auto`，按启用状态、能力声明和优先级选择数据源。
- 数据源 registry 已支持多来源注册和管理，当前产品默认注册来源为 `akshare`、`baostock`、`adata`、`tushare`、`stock_sdk`。
- `akshare` 已作为默认启用适配器接入；本机安装 `akshare` 包后可通过统一 adapter 契约获取 A 股股票列表。
- `baostock` 已作为默认启用适配器接入，支持股票列表和日线行情能力。
- `adata` 已作为默认启用适配器接入，支持股票列表和日线行情能力。
- `tushare` 已作为可选增强适配器接入，需要 `TUSHARE_TOKEN`，默认禁用，不混入通用系统设置。
- `stock_sdk` 已作为可选增强适配器接入，通过 Node.js 调用 `stock-sdk@beta`，默认禁用，需要安装 Node 包后再启用。
- 其他演示型、测试型或未明确纳入第一版的 provider 不作为产品数据源注册或暴露；测试里需要的 fake adapter 只能存在于测试边界内。
- 数据源 adapter 已支持 `provider_metadata`，当前会写入接入类型、文档链接、认证方式、稳定性、限流说明和可选安装说明。
- 股票列表同步已支持 `source=auto`，默认按启用状态、`stock_list` 能力和优先级自动选择 provider；失败会记录尝试日志并降级到下一个来源。
- 后端已提供 `GET /api/data-sources`、`PATCH /api/data-sources/{code}`、`POST /api/data-sources/{code}/health-check`、`POST /api/data-sources/{code}/smoke-test`。
- 数据源检查已拆成两层：`health-check` 用于轻量检查包、凭证和基础接口是否存在；`smoke-test` 会按能力优先级真实拉取小样本并归一化，当前优先 `stock_list`，然后是 `calendars`、`daily_bars`。
- 股票列表、日线行情、交易日历同步已接入标准化 schema 校验和 `ingest_batches` 批次记录；校验失败不会写入主数据，批次会记录实际 provider、请求来源、范围、schema/normalize 版本、原始/标准化/写入行数和错误信息。
- 后端已提供 `GET /api/sync-tasks/{id}/ingest-batches`，用于让前端展示同步任务背后的标准数据整合过程，而不是只能解析日志文本。
- 前端已落地 React + Vite + TypeScript + Ant Design + ProComponents + TanStack Query + TanStack Router。
- 股票池页面已支持列表、搜索、市场/状态筛选、服务端分页、详情 Drawer、同步任务创建、近期任务面板、路由查询参数持久化，以及 loading/error/empty 状态。
- 股票池页面已支持“自动选择（按优先级）”和手动选择启用的数据源，避免把来源写死为单一 provider。
- 同步任务页面已支持状态/来源筛选、服务端分页、路由查询参数持久化、任务详情 Drawer 和任务日志时间线。
- 数据源管理页已支持注册来源展示、provider 接入方式、能力标签、启用/禁用、优先级调整、轻量健康检查、真实取样和按来源创建股票列表同步任务。
- 前端主导航已收敛为五个工作台入口：总控台、股票池、数据源管理、同步调度、数据库管理；旧的日线行情、数据集目录、交易日历和数据质量入口仅作为兼容跳转或领域能力，不再作为产品主导航。
- 前端已引入 GSAP 轻量动画，仅用于后台页面的入场和反馈动效，不作为核心业务依赖。

未完成或暂缓：

- PostgreSQL 迁移、生产部署和数据库运维方案尚未落地；SQLite 仅作为本地开发和 bootstrap fallback。
- Redis、MongoDB 不进入第一阶段核心闭环，除非后续任务队列、缓存或外部兼容需求明确要求。
- AkShare、BaoStock、Tushare、DuckDB 都已纳入 `requirements.txt`；本地未安装对应包时健康状态会显示不可用，日线查询会降级到 PyArrow 读取。
- Tushare 需要 token，当前先通过 `TUSHARE_TOKEN` 接入；后续再补独立的数据源凭证管理，不放进通用系统设置。
- 交易日历已接入基础查询、同步任务和质量检查输入；后续还需要补更细的分来源限流、失败恢复和历史 smoke 记录。
- 数据集目录、交易日历、数据质量和日线行情预览能力已收敛到数据库管理、股票详情和同步调度；后续增强应在五入口内部完成，不重新扩成独立主导航页面。
- daily bars 已支持通过统一 provider fallback 写入 Parquet；行情查询已优先使用 DuckDB 扫描 Parquet 分区，并保留 PyArrow fallback；数据质量已覆盖基础目录检查、必填字段完整率、重复主键、市场级和股票级缺失交易日、OHLC 边界、负价格、负成交量/额。
- 数据库管理已能发现市场级日线覆盖缺口，但市场级补齐任务仍需要独立 `daily_bars_market_repair` API、后端执行逻辑和前端入口；不能复用空 `symbol` 的 `daily_bars`。

第一阶段不适合点：

- 不适合把 PostgreSQL、Redis、MongoDB、Celery 等基础设施一次性作为必需项；第一阶段应先保证本地闭环可运行、可验证。
- 不适合把 AkShare/BaoStock/Tushare 全量能力一次性做齐；应先完成一个真实股票列表同步链路，再扩展日线行情。
- 不适合提前建设完整数据源配置中心、复杂权限、多租户、实盘交易或完整回测引擎。
- 不适合让前端页面直接理解 Parquet/DuckDB 路径或数据源适配器细节；前端仍应只依赖 API 契约。

下一步优先级：

1. 补 `daily_bars_market_repair`：从数据库管理水位线进入同步调度，按 A 股、日期范围和安全阈值创建市场级日线缺口补齐任务。
2. 对 AkShare、BaoStock、Tushare 的真实网络 smoke 补充限流、超时、失败恢复和历史记录；Tushare smoke 需要 `TUSHARE_TOKEN`。
3. 明确 SQLite 到 PostgreSQL 的迁移边界，补最小迁移脚本和可重复验证命令。
4. 继续推进交易日历真实链路 smoke、质量报告明细钻取和质量报告筛选能力，但入口仍放在数据库管理。
5. 在股票详情内继续增强日线图表、常用筛选组合和数据来源追溯，前端仍只依赖 API 契约，不直接理解 Parquet/DuckDB 路径。
6. 视首屏体积和页面数量增长情况，为前端路由补懒加载或 manualChunks，降低 Ant Design/ProComponents 带来的单 chunk 体积。

## 10. 扩展路线

阶段 1：股票数据管理系统

- 总控台
- 股票池
- 数据源管理
- 同步调度
- 数据库管理

阶段 1 内部子能力：

- 交易日历
- 日线行情
- 数据质量
- 数据目录

阶段 2：研究数据系统

- 技术指标
- 因子库
- 财务数据
- 行业数据
- 指数数据
- 数据版本管理

阶段 3：策略和回测

- 策略定义
- 回测任务
- 回测报告
- 组合持仓
- 风险指标
- 参数扫描

阶段 4：交易系统

- 模拟交易
- 券商适配器
- 订单管理
- 风控规则
- 实盘监控

## 11. 工程治理规则

必须遵守：

- 新模块必须先写清楚职责和公开接口。
- 不允许跨模块直接访问内部表、文件或第三方适配器。
- 不允许把数据源配置混入通用系统配置。
- 不允许 API 执行长时间同步任务。
- 不允许前端一次性拉取全量大表。
- 不允许业务代码直接拼接 Parquet 路径。
- 不允许没有 source、updated_at、任务记录的数据写入主数据集。

建议检查清单：

```text
新增一个模块前：
  - 这个模块的职责能否一句话说清？
  - 它依赖哪些模块？
  - 谁会调用它？
  - 它是否泄露了底层数据源或存储细节？

新增一个数据源前：
  - 是否实现 capabilities？
  - 是否有 normalize？
  - 是否有 health_check？
  - 是否声明限流、凭证和字段覆盖范围？

新增一个页面前：
  - 是否对应明确业务模块？
  - 是否使用服务端分页？
  - 是否有 loading、empty、error 状态？
  - 是否没有越过 API 直接理解底层存储？
```

## 12. 已确认和待确认的决策

已确认决策：

- 前端采用 React + Vite + TypeScript + Ant Design + ProComponents。
- 路由采用 TanStack Router。
- 请求、缓存和服务端状态采用 TanStack Query。
- Zustand 只用于主题、布局、用户偏好等轻量 UI 状态。
- 不直接使用完整 Ant Design Pro/Umi 模板作为项目强约束，只复用其设计体系和 ProComponents 能力。

以下决策可以在脚手架前确认：

1. 第一阶段任务执行用 APScheduler/轻量队列，还是直接上 Celery。
2. 本地开发数据库用 Docker PostgreSQL，还是先用 SQLite 快速启动。
3. 股票市场第一版只做 A 股，还是同时预留港股/美股入口。

推荐默认值：

- 任务：第一阶段轻量 worker，后续再升级 Celery。
- 数据库：Docker PostgreSQL。
- 市场：第一版只实现 A 股，但模型保留 market 字段。

## 13. 参考资料

- FastAPI SQL Databases: https://fastapi.tiangolo.com/tutorial/sql-databases/
- PostgreSQL Table Partitioning: https://www.postgresql.org/docs/current/ddl-partitioning.html
- DuckDB Parquet: https://duckdb.org/docs/stable/data/parquet/overview
- Ant Design: https://ant.design/docs/react/getting-started
- Ant Design Pro: https://preview.pro.ant.design/welcome/
- ProComponents: https://procomponents.ant.design/
- Vite: https://vite.dev/guide/
- TanStack Router: https://tanstack.com/router/latest
- TanStack Query: https://tanstack.com/query/latest/docs/framework/react/overview
- Apache ECharts: https://echarts.apache.org/en/index.html
- AkShare: https://github.com/akfamily/akshare
- AkShare stock data docs: https://akshare.akfamily.xyz/data/stock/stock.html
- BaoStock: http://baostock.com
- Tushare Pro docs: https://tushare.pro/document/2
- vn.py datafeed interface: https://github.com/vnpy/vnpy/blob/master/vnpy/trader/datafeed.py
- Qlib data layer: https://qlib.readthedocs.io/en/latest/component/data.html
- Qlib data collector: https://github.com/microsoft/qlib/tree/main/scripts/data_collector
- Zipline bundles: https://zipline.ml4trading.io/bundles.html
- OpenBB provider standardization: https://docs.openbb.co/odp/python/developer/standardization
- QuantConnect LEAN security identifiers: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/security-identifiers
- QuantConnect LEAN equity data normalization: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data
- QuantConnect LEAN corporate actions: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions
- backtrader data feeds reference: https://www.backtrader.com/docu/dataautoref/
- backtrader Cerebro data feed usage: https://www.backtrader.com/docu/cerebro/
