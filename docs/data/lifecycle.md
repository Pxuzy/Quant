# 股票数据全生命周期管理

> 本文档是当前股票数据治理的权威入口。代码和测试描述当前行为；本文档描述边界、契约和演进方向。若与历史设计文档冲突，以当前代码、测试和本文档为准。

## 1. 当前范围

Quant 当前是本地优先的 A 股股票研究工作台，数据治理范围包括：

- 股票基础资料；
- 交易日历；
- 日线 OHLCV；
- 数据源、同步任务、入库批次、质量报告和批次级血缘；
- 面向研究和回测的最小 `BarReader` 读取契约。

当前不把实盘下单、完整回测引擎、实时行情和新闻抓取误写成同一条正式主数据管线。`/api/market` 的实时/展示读取是独立边界；后续若纳入治理，必须另立数据契约。

## 2. 真实代码入口

| 能力 | 当前路径 |
| --- | --- |
| FastAPI 应用 | `backend/app/main.py` |
| 数据源适配器 | `backend/app/adapters/` |
| 同步服务 | `backend/app/services/stock_sync_service.py`、`sync_service.py`、`trading_calendar_service.py` |
| 日线入库管线 | `backend/app/services/daily_bar_ingest_pipeline.py` |
| 日线存储/查询 | `backend/app/repositories/daily_bars.py`、`backend/app/db/duckdb_store.py` |
| Worker | `backend/worker/sync_stocks.py` |
| 前端 | `frontend/` |
| 测试 | `tests/api/`、`tests/worker/`、`tests/web/` |

历史文档中的 `apps/api`、`apps/web`、`apps/worker`、`quant/` 不表示当前仓库目录。

## 3. 当前正式生命周期

当前 API/Worker 的日线正式链路是：

```text
sync_tasks
  -> worker claim pending task
  -> provider candidate selection
  -> provider health_check（执行阶段）
  -> adapter.fetch_daily_bars
  -> immutable raw artifact + checksum
  -> adapter.normalize_daily_bars
  -> validate_daily_bar_records
  -> ingest_batches
  -> DuckDB write + Parquet silver archive
  -> datasets update
  -> task/batch success or failure
  -> BarReader / API / UI
```

任务创建阶段只要求 provider 已注册、启用并声明所需能力；provider 不可用属于执行阶段失败，必须保留 task、log 和 batch 记录，而不是让入队请求消失。

### 当前已实现

- `NormalizedStock`、`NormalizedDailyBar`、`NormalizedTradingCalendar` 标准化对象；
- 股票、日线和交易日历的写入前校验；
- `(symbol, exchange, market, trade_date, adjust_type)` 日线幂等键；
- `sync_tasks`、`sync_task_logs`、`ingest_batches`、`datasets`、`data_quality_reports`；
- `GET /api/database/lineage` 的批次级血缘；
- `GET /api/research-data/bars` 的单股票 governed-only `BarReader`；
- 单股票日线正式 fetch 的 raw envelope、SHA-256 和 `IngestBatch.raw_artifact_id` 关联；
- `daily_bars_raw_replay` worker task：校验 raw checksum 后离线 normalize，不重新请求 provider；
- provider 退役记录保留：当前 registry 不再删除历史 `DataSource`，而是标记为 retired 并从默认运行列表隐藏；
- 不同 data lake 的 DuckDB 路径隔离；重复写入返回实际新增行数。

### 尚未实现或不应误称已完成

- 独立 `dataset_versions`、`dataset_partitions`、`snapshots` 和持久 manifest；
- 以质量检查为阻断条件的 candidate → active 原子发布；
- 物化 watermark、provider attempt、quarantine 记录；
- 完整 DataPortal、多股票批量读取、列投影和固定回测 snapshot。

`scripts/ops/` 下的 raw → silver 脚本是旁路运维工具，不等价于 API/Worker 正式生命周期；在正式 replay 接入前不得把它们描述为同一条已闭环管线。

## 4. 数据层语义

| 层 | 当前语义 | 研究是否可直接读取 |
| --- | --- | --- |
| raw | 日线、股票列表、交易日历和市场 repair 正式 fetch 已保存 raw envelope | 否 |
| bronze | 目标层，当前没有正式自动发布逻辑 | 否 |
| silver | 当前日线 canonical 查询/归档层 | 是，受 governed contract 约束 |
| gold | 目标层，用于因子、指标和回测专用数据集 | 未来 |

当前 DuckDB 与 Parquet 都参与日线流程。仓库演进方向是：Parquet silver/gold 成为权威数据集，DuckDB 作为可重建的查询/扫描引擎，而不是另一份不可解释的权威副本。任何切换都必须增加一致性、重建和回滚测试。

## 5. Provider 与来源语义

当前默认 registry 只注册：

- `akshare`：股票列表、日线；
- `baostock`：股票列表、日线、交易日历；
- `stock_sdk`：股票列表、日线，默认关闭。

AData、Tushare 当前没有正式 adapter，不得写入“当前可用 provider”清单。`source=auto` 是请求策略，不是实际来源；成功 batch 必须在 `ingest_batches.source` 记录最终 provider，`requested_source` 才记录用户请求的 `auto` 或手动来源。

provider 退出 registry 后：

1. 不再参与新的自动候选；
2. 默认数据源 API 列表隐藏退役项；
3. 数据库保留历史记录并标记 `retired`；
4. 历史 batch、lineage 和报告仍能解释原始来源。

## 6. 时间与复权契约

- `trade_date` 是交易所本地交易日日期，不带时区；
- `fetched_at`、`ingested_at`、`checked_at` 等系统事件时间统一使用 UTC；
- A 股市场时区语义为 `Asia/Shanghai`；
- 交易日历是缺口判断的权威来源；
- `adjust_type` 当前为 `none`、`qfq`、`hfq`，必须进入日线身份键和读取契约；
- 同一 dataset version 不得混合未声明的复权口径；
- 当前 `adjust_factor=1.0` 不代表已经完成完整分红、拆股和公司行动复权。

后续建设公司行动时，应独立建模分红、拆并股、改名、退市和复权因子，不把这些语义隐含在普通 OHLCV 字段中。

## 7. 质量与发布边界

当前有两级校验：

1. `validate_*_records`：写入前的字段、类型、市场、日期、OHLC、重复键等硬校验；
2. `DataQualityService.run_check()`：对已登记数据集执行完整检查并产生历史报告，包括重复、缺失交易日、OHLC 边界、负值和股票池覆盖。

当前完整质量检查仍是独立检查入口，不应写成每次 ingest 自动执行的 fail-closed 发布门禁。目标流程是：

```text
raw artifact
  -> normalize
  -> schema validation
  -> silver candidate
  -> quality gate
  -> manifest/version publish
  -> active snapshot
```

质量阻断时不得推进 active dataset；质量 warning 可以发布，但必须记录在 manifest 和报告中。

## 8. 研究读取边界

研究、因子、回测和策略代码不得：

- 直接 import provider adapter；
- 直接调用 AKShare、BaoStock 等外部接口；
- 直接读取底层数据库表；
- 直接拼接 Parquet 路径；
- 自行决定未声明的复权口径；
- 绕过质量状态或 snapshot。

当前 `BarReader` 只保证单股票、市场、日期范围和分页读取，并返回由 `Dataset` 与最新成功 `IngestBatch` 组成的内联 manifest。目标契约应增加 `dataset_version`、`snapshot_id`、schema hash、quality policy 和 lineage reference。

## 9. 目标架构

```text
source registry
  -> fetch task / provider attempt
  -> immutable raw artifact
  -> bronze（可选轻量层）
  -> normalize + schema contract
  -> silver candidate
  -> quality gate
  -> dataset version + manifest + partitions
  -> active snapshot
  -> catalog + lineage + watermark
  -> BarReader / DataPortal
  -> factor / backtest / strategy
```

适合个人项目的增量顺序：

1. 冻结 provider registry 与数据契约；
2. 增加质量门禁和原子发布；
3. 增加 dataset version、manifest、snapshot、watermark；
4. 扩展 BarReader/DataPortal；
5. 最后统一 replay 的 API、lease/retry 和运维观测。

暂不引入 Kafka、Airflow、Celery、Redis、Iceberg/Delta 或微服务拆分。

## 10. 外部项目借鉴边界

这些项目均低于用户偏好的 100k stars，因此只因相关性借鉴局部设计，不作为“高星项目推荐”：

- [Qlib](https://github.com/microsoft/qlib)：46k+ stars；借鉴本地标准数据层、DataHandler/Dataset 与研究读取边界；
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean)：20k+ stars；借鉴 raw/adjusted normalization 语义显式化；
- [Zipline](https://github.com/quantopian/zipline)：19k+ stars；借鉴 bundle ingest、可重复加载和 ingest 时间记录；
- [OpenBB](https://github.com/OpenBB-finance/OpenBB)：70k+ stars；借鉴 provider metadata、统一参数/数据模型和 validator 边界。

不直接复制这些项目的完整平台、策略引擎或调度基础设施。
