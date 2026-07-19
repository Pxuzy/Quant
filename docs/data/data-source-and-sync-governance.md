# 数据源和同步治理

> 本文档只描述当前实现与已确认的治理规则。当前代码的真实入口在 `backend/app`、`backend/worker` 和 `frontend`；历史 `apps/api`、`apps/web`、`apps/worker` 路径不适用于当前仓库。

## 1. 当前正式 provider registry

唯一正式 registry：`backend/app/adapters/registry.py`。

| code | 当前能力 | 默认状态 | 说明 |
| --- | --- | --- | --- |
| `akshare` | `stock_list`、`daily_bars` | 启用 | 公开数据源；运行时仍需检查可选依赖和可用性 |
| `baostock` | `stock_list`、`daily_bars`、`calendars` | 启用 | A 股股票、日线和交易日历 |
| `stock_sdk` | `stock_list`、`daily_bars` | 关闭 | Node 社区包，需额外运行环境 |

AData、Tushare 当前没有正式 adapter 文件，不得作为当前自动同步 provider。若未来接入，必须先实现 adapter、capability、metadata、health、normalize、测试和授权说明。

`GET /api/data-sources/catalog` 是候选目录，不是正式 registry；当前代码中候选目录为空，不应将社区 MCP 直接视为数据权威源。

## 2. 来源选择规则

- 手动指定来源时，任务记录请求的 provider code；
- `source=auto` 只表示请求策略，不是实际写入来源；
- 任务创建只检查 provider 已注册、启用和声明能力；
- provider health check 在 worker 执行阶段进行；不可用时任务进入失败生命周期并留下日志/批次；
- 自动执行按启用状态、能力、健康状态、优先级和历史成功率选择；
- 成功写入必须把最终 provider 写入 `ingest_batches.source`，并将用户请求写入 `requested_source`；
- provider fallback 不得静默混源，至少要在 task log、batch 和质量/manifest 元数据中可见。

provider 从 registry 退役时，不删除历史 `DataSource`：

- `enabled=false`；
- `health_status=retired`；
- `config_json.retired=true`；
- 默认运行列表隐藏退役项；
- 历史 batch、lineage 和质量报告仍可引用该来源。

## 3. 当前同步任务

| task type | API 入口 | 当前作用 |
| --- | --- | --- |
| `stock_list` | `POST /api/stocks/sync` | 股票池 upsert 到 metadata database |
| `daily_bars` | `POST /api/market-data/daily-bars/sync` | 单股票日线同步 |
| `daily_bars_market_repair` | `POST /api/market-data/daily-bars/market-repair` | 按股票池、交易日历和缺口计划执行市场级修复 |
| `calendars` | `POST /api/trading-calendars/sync` | 交易日历同步 |

任务执行入口：`backend/worker/sync_stocks.py`。`daily_bars_raw_replay` 已作为 worker/CLI task type 实现；它只读取 `raw_artifacts`，不访问 provider。当前尚无 replay API；replay 只能通过受控 worker/CLI 入口执行。

## 4. 当前正式接入链路

```text
sync task
  -> worker claim
  -> provider health_check
  -> adapter.fetch
  -> raw artifact envelope + checksum（当前已接入日线、股票列表、交易日历和市场 repair）
  -> adapter.normalize
  -> schema validation
  -> ingest_batch
  -> DuckDB write + Parquet silver archive
  -> dataset metadata update
  -> task/batch result
  -> quality report / lineage / BarReader
```

当前日线、股票列表、交易日历和市场级 repair 正式管线会在 normalize 前保存 provider raw envelope，并通过 `raw_artifacts` 与 `ingest_batches.raw_artifact_id` 关联。日线 artifact 同时保存实际 `adjust_type`，replay 不允许仅改标签而不做真实价格换算。历史旁路 raw/silver 脚本已删除，持久化采集统一进入 `sync_tasks`、`ingest_batches`、quality 和 lineage。

目标正式链路：

```text
fetch
  -> immutable raw artifact + checksum
  -> normalize
  -> schema contract
  -> silver candidate
  -> quality gate
  -> dataset version/manifest publish
  -> active snapshot
```

离线 replay 命令示例：

```bash
python -m backend.worker.sync_stocks \
  --task-type daily_bars_raw_replay \
  --raw-artifact-id <artifact_id> \
  --adjust-type qfq \
  --enqueue
python -m backend.worker.sync_stocks --run-next-pending
```

相同 raw artifact 与规范化后的 `adjust_type` 只能存在一个 pending/running replay；该保证由数据库局部唯一索引原子执行。已结束的 replay 可以显式重新创建，以保留新的执行审计记录。

## 5. 日线契约

日线标准字段由 `NormalizedDailyBar` 和 `DAILY_BAR_SCHEMA` 共同定义：

- `symbol`：系统标准代码；
- `exchange`：标准交易所；
- `market`：标准市场，当前重点为 `A_SHARE`；
- `trade_date`：交易日；
- `open/high/low/close`：OHLC；
- `pre_close`、`volume`、`amount`；
- `adjust_factor`；
- `adjust_type`：`none`、`qfq`、`hfq`；
- `source`：实际 provider；
- `ingested_at`：UTC 入库时间。

当前日线幂等身份键：

```text
(symbol, exchange, market, trade_date, adjust_type)
```

不同复权口径必须作为不同记录处理，不能互相覆盖。重复写入返回实际新增记录数；重复请求不应虚增 `records_written`。

## 6. 质量、批次和血缘

写入前硬校验覆盖：

- 必填字段与类型；
- 市场、交易所和代码标准化；
- 日期范围；
- OHLC 边界；
- 非负价格、成交量和成交额；
- 重复身份键。

`DataQualityService.run_check()` 另行检查：

- 字段完整率；
- 重复主键；
- 市场级和股票级缺失交易日；
- OHLC 边界；
- 负值；
- 股票池覆盖。

当前完整质量检查是独立检查流程，不应误写为每次 ingest 自动阻断发布。当前 lineage 是 `SyncTask + IngestBatch` 级别，不是逐行或字段级 lineage。

## 7. 运维边界

- 长时间同步必须先创建 `sync_tasks`，再由 worker 执行；
- provider 失败必须记录错误原因、task、batch 和日志；
- 市场修复不得用空 `symbol` 的普通 `daily_bars` 任务伪装；
- 历史旁路采集脚本已删除，不再维护第二套 raw/silver 写入入口；
- 研究、因子、回测和策略只能通过 API、silver/gold 数据集或 `BarReader` 获取数据，不能直连 provider 或拼 Parquet 路径。

## 8. 未来治理增量

1. raw artifact 保留期、清理策略和 orphan/reconcile 运维；
2. provider attempt、retry 和错误分类；
3. quality run/result 与 candidate → active 原子发布；
4. dataset version、partition manifest、snapshot 和 watermark；
5. replay 已实现只读取 raw、不访问 provider；后续补充失败恢复和运维观测；
6. BarReader 扩展多股票、列投影、snapshot 和质量策略。
