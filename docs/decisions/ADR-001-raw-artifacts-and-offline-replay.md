# ADR-001：正式采集必须保留不可变 Raw Artifact

## 状态
已接受

## 日期
2026-07-18

## 背景

项目原有 API/Worker 正式同步路径是：

```text
provider fetch -> normalize -> schema validation -> DuckDB/Parquet + metadata
```

这使得 provider 字段变更、normalizer 修复、复权口径调整或质量规则升级后，必须再次请求第三方数据源才能重新处理历史数据。旁路 `scripts/ops` 虽会产生 raw 文件，但它未稳定关联 `sync_tasks`、`ingest_batches`、checksum 与 batch lineage，不能作为正式回放依据。

约束条件：

- 保持 FastAPI + SQLAlchemy + SQLite/PostgreSQL + Parquet/DuckDB 的模块化单体；
- 本地优先，不能引入 Kafka、Airflow、Iceberg、Delta 或对象存储基础设施；
- 保证 provider 原始响应可以离线审计和 replay；
- 不能把物理 lake 路径暴露给研究、回测或前端读取层。

## 决策

### Raw artifact 格式与位置

正式 fetch 在调用 normalizer 前将 provider 响应持久化为 JSON envelope：

```text
DATA_LAKE_DIR/raw/<dataset>/source=<provider>/task=<task_id>/symbol=<symbol>-<sha256-prefix>.json
```

文件采用确定性 JSON 序列化，包含：

- format/version；
- dataset、task、provider、requested source；
- market、symbol、请求日期范围；
- row_count；
- 原始 records。

写入采用临时文件 + `fsync` + `os.replace`，避免正常成功路径看到半成品文件。

### 元数据与血缘

新增 `raw_artifacts`：

- 来源 task、dataset、source、requested_source；
- 市场、股票、日期范围；
- `uri`、SHA-256、byte size、row count、content type、status；
- 创建时间。

`ingest_batches.raw_artifact_id` 关联该输入，因此 batch lineage 可以追溯到原始 provider 响应。当前 API 的 task batch 读取与数据库 lineage 可见 batch 的 raw artifact ID；物理路径仍只留在后端元数据，不作为研究数据契约的一部分。

### 覆盖范围

当前已经接入：

- `stock_list`；
- `daily_bars`；
- `daily_bars_market_repair` 的每只股票写入；
- `calendars`。

### Replay

新增 `daily_bars_raw_replay` worker/CLI 任务。它：

1. 读取 `raw_artifacts` 中的输入 artifact；
2. 校验 SHA-256 与记录数；
3. 使用记录的 provider adapter 做本地 normalize；
4. 必须沿用 artifact 已记录的 `adjust_type`；离线 replay 不执行价格复权换算，因此不同口径请求会失败；
5. 通过标准 ingest batch 路径写回 canonical 日线；
6. **不请求任何 provider**。

当前没有 HTTP replay API，避免未审计的用户输入直接触发数据重写；replay 由受控 worker/CLI 执行。

## 备选方案

### 只保留 `scripts/ops` 的 raw 文件

- 优点：没有元数据迁移；
- 缺点：不与 task、batch、checksum、lineage 统一，无法可靠审计或回放；
- 结论：拒绝。

### 每次 normalize 修复后重新请求 provider

- 优点：实现最少；
- 缺点：历史数据随上游变化、限流、凭证、下线和网络状态而不可复现；
- 结论：拒绝。

### 直接引入 Iceberg/Delta/Kafka/Airflow

- 优点：可获得成熟的数据湖/调度能力；
- 缺点：显著超出个人项目当前规模和运维约束；
- 结论：暂不采用。

## 后果

正面：

- 正式采集可追溯、可离线回放；
- normalizer、复权口径和 schema 改进不必重新下载数据；
- provider 原始输入、batch 与 canonical 输出关系明确；
- 为 dataset version、quality gate、snapshot 和 quarantine 奠定输入边界。

限制与后续：

- raw 保留期、清理策略和 snapshot 引用保护尚未实现；
- raw 文件与 SQL metadata 是可恢复的跨存储边界，不是单一 ACID 事务；若 DuckDB 已写入而后续 metadata 更新失败，batch 会标记 `reconcile_required`，不得将其误解为可自动回滚；
- `raw_artifacts` 还未有独立 API 展示层；
- replay 当前只支持日线，不覆盖股票池或交易日历；
- raw 文件可能包含 provider 返回的额外字段，日志和 API 不得直接暴露完整 payload；
- 元数据引用在 SQLite 和 PostgreSQL 均使用 `ON DELETE RESTRICT`；SQLite 连接显式启用 `PRAGMA foreign_keys=ON`，避免把声明的外键误当作实际执行的约束。
- 完整质量门禁、candidate/active 发布和不可变 dataset version 仍为后续 ADR。
