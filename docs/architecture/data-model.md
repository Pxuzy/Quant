# 数据模型

本文档依据 `apps/api/models/entities.py` 整理当前核心实体。

## 实体总览

| 实体 | 表名 | 职责 |
| --- | --- | --- |
| `Stock` | `stocks` | 股票池基础资料 |
| `DataSource` | `data_sources` | 数据源配置、启用状态、优先级和健康状态 |
| `SyncTask` | `sync_tasks` | 同步任务生命周期 |
| `SyncTaskLog` | `sync_task_logs` | 任务执行日志 |
| `SyncSchedule` | `sync_schedules` | 定时同步配置和手动触发配置 |
| `IngestBatch` | `ingest_batches` | 正式写入批次、来源、范围、版本和质量状态 |
| `Dataset` | `datasets` | 数据集目录和最新状态 |
| `TradingCalendar` | `trading_calendars` | 市场交易日历 |
| `DataQualityReport` | `data_quality_reports` | 数据质量检查结果 |

## 关键关系

```text
SyncTask
  -> SyncTaskLog
  -> IngestBatch

Dataset
  -> latest_data_date
  -> quality_status
  -> schema_json

DataQualityReport
  -> dataset_name
```

## 股票池

`stocks` 使用 `(symbol, exchange, market)` 作为唯一身份。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `symbol` | 系统内部股票代码，如 `600519` |
| `exchange` | 交易所，如 `SSE`, `SZSE`, `BSE` |
| `market` | 市场，如 `A_SHARE` |
| `name` | 股票名称 |
| `status` | 上市状态 |
| `industry` | 行业 |
| `listing_date` | 上市日期 |
| `source` | 数据来源 |

## 数据源

`data_sources` 管理 provider 的运行状态，不存放通用系统设置。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `code` | `akshare`, `baostock`, `adata`, `tushare`, `stock_sdk` |
| `enabled` | 是否参与自动选择 |
| `priority` | 自动选择优先级 |
| `requires_token` | 是否需要凭证 |
| `config_json` | provider 元信息和配置 |
| `health_status` | 健康状态 |

## 同步任务

`sync_tasks` 记录用户和系统创建的同步请求。

支持任务类型：

| 类型 | 说明 |
| --- | --- |
| `stock_list` | 股票池同步 |
| `daily_bars` | 单股日线同步 |
| `daily_bars_market_repair` | 市场级缺口补齐 |
| `calendars` | 交易日历同步 |

关键字段：

| 字段 | 说明 |
| --- | --- |
| `source` | 请求来源，可能为 `auto` |
| `market` | 市场 |
| `symbol` | 股票代码，单股日线必须填写 |
| `start_date`, `end_date` | 同步范围 |
| `status` | `pending`, `running`, `success`, `failed`, `canceled` |
| `records_read`, `records_written` | 读取和写入数量 |
| `error_message` | 失败原因 |

## 入库批次

`ingest_batches` 是数据可追溯的核心表。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `task_id` | 对应同步任务 |
| `dataset_name` | 写入的数据集 |
| `source` | 实际 provider |
| `requested_source` | 用户请求来源，可能为 `auto` |
| `schema_version` | 数据契约版本 |
| `normalize_version` | 标准化版本 |
| `raw_records` | 原始记录数 |
| `normalized_records` | 标准化记录数 |
| `records_written` | 写入记录数 |
| `validation_errors_json` | 校验错误 |
| `quality_status` | 质量状态 |

## 数据集目录

`datasets` 记录系统管理的数据资产。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `name` | 数据集名称 |
| `layer` | `raw`, `bronze`, `silver`, `gold` |
| `storage_type` | `postgres`, `sqlite`, `parquet` 等 |
| `path` | 数据湖路径，前端不得直接依赖 |
| `schema_json` | schema 摘要 |
| `primary_keys_json` | 主键 |
| `partition_keys_json` | 分区键 |
| `row_count` | 行数 |
| `latest_data_date` | 最新数据日期 |
| `quality_status` | 质量状态 |

## 交易日历

`trading_calendars` 使用 `(market, trade_date)` 唯一约束。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `market` | 市场 |
| `trade_date` | 日期 |
| `is_open` | 是否开市 |
| `source` | 数据来源 |

## 数据质量报告

`data_quality_reports` 记录检查项结果。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `dataset_name` | 数据集 |
| `check_type` | 检查类型 |
| `status` | 检查状态 |
| `severity` | 严重级别 |
| `metric_name` | 指标名称 |
| `metric_value` | 实际值 |
| `expected_value` | 期望值 |
| `message` | 可读说明 |
