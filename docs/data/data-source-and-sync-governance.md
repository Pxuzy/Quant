# 数据源和同步治理

## 数据源清单

当前默认注册的数据源来自 `apps/api/adapters/registry.py`。

| code | 用途 | 默认定位 |
| --- | --- | --- |
| `akshare` | 股票列表等公开数据 | 默认启用基础来源 |
| `baostock` | 股票列表、日线等 A 股数据 | 默认启用基础来源 |
| `adata` | 股票列表、日线等公开数据 | 默认启用基础来源 |
| `tushare` | 专业增强数据源 | 需要 `TUSHARE_TOKEN`，默认可选 |
| `stock_sdk` | Node 侧社区包来源 | 需要安装 `stock-sdk@beta` 或配置 `STOCK_SDK_CWD` |

## provider 选择规则

- 手动指定来源时，任务使用指定 provider。
- `source=auto` 表示自动选择，不是实际 provider。
- 自动选择按启用状态、能力声明、优先级和健康状态选择候选 provider。
- 每次正式写入都必须在 `ingest_batches.source` 记录实际 provider。
- 禁用的数据源不参与自动选择。

## 数据接入链路

```text
adapter.fetch
  -> adapter.normalize
  -> schema_validate
  -> ingest_batch
  -> write storage
  -> quality_check
  -> catalog and lineage
```

## 标准化和校验

正式数据写入前必须完成：

- 字段标准化。
- 市场、交易所和股票代码标准化。
- 必填字段校验。
- 日期范围校验。
- 数值口径校验。
- source 和任务批次记录。

日线数据至少要明确：

| 字段 | 要求 |
| --- | --- |
| `symbol` | 系统内部代码 |
| `exchange` | 标准交易所 |
| `market` | 标准市场 |
| `trade_date` | 交易日期 |
| OHLCV | 开高低收和成交量 |
| `amount` | 成交额 |
| `adjust_type` | 复权口径 |
| `source` | 实际来源 |
| `ingested_at` | 入库时间 |

## 同步任务类型

| 任务类型 | 创建入口 | 执行逻辑 |
| --- | --- | --- |
| `stock_list` | `POST /api/stocks/sync` | 同步股票池，upsert 到 `stocks` |
| `daily_bars` | `POST /api/market-data/daily-bars/sync` | 单股日线写入 Parquet |
| `daily_bars_market_repair` | `POST /api/market-data/daily-bars/market-repair` | 按股票池和交易日历计算缺口后补齐 |
| `calendars` | `POST /api/trading-calendars/sync` | 同步交易日历 |

## 定时配置

当前默认定时配置来自 `apps/api/repositories/sync_schedules.py`。

| code | 名称 | 任务类型 | 默认状态 |
| --- | --- | --- | --- |
| `daily_bars_after_close` | 每天收盘后更新日线 | `daily_bars` | 禁用 |
| `weekly_stock_pool` | 每周更新股票池 | `stock_list` | 禁用 |
| `monthly_calendar_backfill` | 每月补齐交易日历 | `calendars` | 禁用 |

第一版只管理配置和手动触发，不启动真实 cron 执行器。

## 市场级日线缺口补齐

市场级补齐必须使用 `daily_bars_market_repair`：

- 从数据库管理识别覆盖缺口。
- 在同步调度中预览补齐计划。
- 按市场、日期范围、安全上限创建任务。
- 后端根据股票池、交易日历和已有日线生成缺口计划。
- 每只股票或每批数据形成可追溯入库批次。

禁止用空 `symbol` 的 `daily_bars` 代表全市场补齐。

## 数据质量治理

当前质量能力覆盖：

- 数据集目录检查。
- 必填字段完整率。
- 重复主键。
- 市场级和股票级缺失交易日。
- OHLC 边界。
- 负价格。
- 负成交量和负成交额。

质量结果写入 `data_quality_reports`，并在数据库管理和股票详情中展示。

## 血缘和目录

血缘查询来自 `GET /api/database/lineage`，核心来源是 `ingest_batches`。

数据集目录来自 `datasets`，用于展示：

- 数据集名称。
- 存储介质。
- schema 摘要。
- 分区键。
- 行数。
- 最新日期。
- 质量状态。

## 治理原则

- 正式数据必须可追溯到任务和批次。
- 失败任务必须有日志和错误原因。
- 多 provider fallback 不能静默混源。
- 数据湖路径只由后端和数据层管理。
- 后续因子、回测、策略只能消费统一数据服务。
