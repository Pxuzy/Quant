# Dataset Version、Manifest、Snapshot 与离线回测输入规格

> 状态：设计已确认，尚未实现
>
> 目标：在现有 `raw_artifact -> ingest_batch -> Dataset -> BarReader` 旁边增加不可变发布层，不重写当前 FastAPI、Worker、DuckDB 和 Parquet 主链。

## 1. 当前事实与阻断

当前 `Dataset` 是可变目录/状态摘要，不是不可变版本；`ResearchDataService._daily_bars_manifest()` 是实时拼装的摘要，不包含固定 partition 清单、文件 checksum、schema hash 和版本 ID。

当前日线 Parquet 使用固定路径并可能原地合并覆盖：

```text
silver/daily_bars/market=A_SHARE/trade_date=YYYY-MM-DD/part-000.parquet
```

因此在实现正式 snapshot 前，现有路径只能作为 legacy/archive 读取面，不能直接登记为 published immutable partition。

## 2. 目标链路

```text
provider fetch
  -> immutable raw artifact
  -> normalize / schema validation
  -> ingest batch
  -> immutable version partition materialization
  -> candidate DatasetVersion
  -> checksum / row-count / schema / quality gate
  -> published manifest
  -> active Snapshot pointer
  -> snapshot-bound BarReader
  -> offline BacktestRun
```

原则：

- version/partition/manifest/snapshot 不可变；active 只是可移动指针；
- 研究和回测只能消费已发布 snapshot；
- 旧 snapshot 在新版本发布后读取结果不变；
- 任何 checksum、文件、row count、日期范围或质量校验失败都 fail closed；
- 文件先以不可变路径完成，数据库指针最后在单事务中切换；跨文件系统和 SQL 不宣称 ACID 回滚；
- 失败 candidate 可清理或进入 orphan/reconcile，不得污染旧 active。

## 3. 最小实体

### 3.1 `dataset_versions`

逻辑数据集的不可变候选/发布记录：

```text
id                         UUID/ULID 或稳定字符串
 dataset_id                FK datasets.id
version_seq                dataset 内单调序号
version_key                稳定内容身份
status                     candidate/validating/ready/published/rejected/failed/retired
created_from_batch_id      FK ingest_batches.id
schema_version
schema_sha256
normalize_version
adjust_type
quality_policy_version
quality_status
quality_checked_at
row_count
min_trade_date
max_trade_date
manifest_uri
manifest_sha256
failure_reason
created_at
published_at
```

约束：

```text
UNIQUE(dataset_id, version_seq)
UNIQUE(dataset_id, version_key)
UNIQUE(dataset_id, manifest_sha256)
```

不变量：

1. `published`、`retired` 字段不可更新；修复产生新 version。
2. `row_count` 等于全部 sealed partition 的 row count 总和。
3. `manifest_sha256 = sha256(canonical_manifest_bytes)`。
4. version 只能声明一个 `adjust_type`、schema 和 normalize 版本。
5. published 前必须存在 manifest、所有 partition sealed、checksum/row count 验证通过且无 error 级质量报告。
6. rejected/failed version 不能被 snapshot 引用。

### 3.2 `dataset_version_partitions`

```text
id
 dataset_version_id        FK dataset_versions.id
partition_spec_json        规范化 partition key
relative_uri               相对于受控 lake root
sha256
byte_size
row_count
min_trade_date
max_trade_date
ingest_batch_id             FK ingest_batches.id
status                     staged/sealed/missing/corrupt
created_at
```

约束：

```text
UNIQUE(dataset_version_id, partition_spec_json, relative_uri)
```

`relative_uri` 禁止绝对路径和 `..` escape；sealed 后文件不能原地覆盖。

### 3.3 Manifest

第一阶段不单独建立 `dataset_manifests` 表；由 version metadata 和不可变 JSON 文件共同构成：

```json
{
  "manifest_version": "v1",
  "dataset": "daily_bars",
  "dataset_version_id": "...",
  "schema_version": "v1",
  "normalize_version": "v1",
  "schema_sha256": "...",
  "adjust_type": "none",
  "primary_keys": ["symbol", "exchange", "market", "trade_date", "adjust_type"],
  "partition_keys": ["market", "trade_date"],
  "row_count": 123,
  "min_trade_date": "2026-06-01",
  "max_trade_date": "2026-06-30",
  "quality": {"status": "good", "policy": "daily-bars-v1"},
  "lineage": {"ingest_batch_ids": [123], "raw_artifact_ids": [456]},
  "partitions": [
    {
      "key": {"market": "A_SHARE", "trade_date": "2026-06-01"},
      "uri": "versions/.../market=A_SHARE/trade_date=2026-06-01/part-000.parquet",
      "sha256": "...",
      "byte_size": 100,
      "row_count": 10
    }
  ]
}
```

canonical 规则：UTF-8、JSON key 排序、固定日期格式、无绝对路径、不把 `generated_at` 等非确定字段纳入 hash。

### 3.4 `snapshots` 与 `snapshot_members`

```text
snapshots
  id
  name
  status draft/active/retired/failed
  created_at
  activated_at
  retired_at

snapshot_members
  snapshot_id       FK snapshots.id
  dataset_id        FK datasets.id
  dataset_version_id FK dataset_versions.id
  role              bars/calendar/universe
```

主键：`(snapshot_id, dataset_id)`。

不变量：

- active snapshot 只能引用 published version；
- snapshot 激活后 members 不可修改；
- 同一 dataset 在一个 snapshot 中只能出现一次；
- 被回测引用的 snapshot 不可删除；
- BarReader 在请求开始时解析一次 snapshot，分页不得重新解析 latest/active。

### 3.5 `datasets.active_snapshot_id`

保持 nullable 以兼容旧库。它是交互读取的默认入口，不是回测的历史输入。回测必须保存明确 `snapshot_id`。

## 4. 发布状态机

```text
candidate -> validating -> ready -> published -> retired
                 |             |
                 +-> rejected  +-> failed
```

- validation infrastructure failure：`failed`；
- quality error：`rejected`；
- warning 可进入 `ready`，manifest 必须保留 warning；
- published 不得回退 candidate；
- active snapshot 切换在 SQL 事务中完成：校验 members → 设置新 active → 旧 active retired → commit。

## 5. 失败补偿

| 失败点 | 处理 |
|---|---|
| version staging 文件失败 | version failed；清理 staging；清理失败则登记 orphan |
| partition 缺失/损坏 | partition corrupt，version failed，不发布 |
| manifest 已写但 metadata 失败 | orphan manifest；按 version/hash 扫描后幂等登记或回收 |
| quality error | version rejected，旧 active 不变 |
| publish 成功但 snapshot 激活失败 | version 保持 published，旧 snapshot 保持 active，可重试激活 |
| DuckDB/Parquet 与 SQL metadata 不一致 | batch/version 标记 reconcile_required；从 raw replay 重建新 candidate |
| BarReader checksum/文件失败 | 请求失败，绝不回退到 latest/active |

## 6. API 与读取边界

现有接口保留兼容：

```text
GET /api/datasets
GET /api/datasets/{name}
GET /api/research-data/bars
```

增量字段：

```json
{
  "active_snapshot_id": "...",
  "active_version_id": "...",
  "manifest_sha256": "..."
}
```

后续只读接口：

```text
GET /api/datasets/{name}/versions
GET /api/datasets/{name}/versions/{version_id}/manifest
GET /api/snapshots/{snapshot_id}
```

BarReader：

- `snapshot_id` 指定时严格读取该 snapshot；损坏或不存在直接失败；
- 未指定时只允许交互场景解析 active，并在响应返回实际 snapshot ID；
- `adjust_type` 必须与 version/manifest 一致；
- 未来批量读取使用 `symbols + fields` 白名单，服务端执行列投影。

回测服务只能依赖 `BarReader` 协议，不得依赖 provider、DailyBarRepository、DuckDBStore 或直接拼 Parquet 路径。

## 7. 实施切片

### Slice 0：BarReader 复权契约

- repository 接受并过滤 `adjust_type`；
- 单股票 API 继续兼容；
- 测试 none/qfq 混合、非法口径、分页计数和 DuckDB/PyArrow 等价。

### Slice 1：单一 `daily_bars` version + manifest

- 增加 version/partition 表；
- 将现有 governed 数据 materialize 到版本目录，不登记可覆盖的 legacy `part-000.parquet`；
- 生成 canonical manifest 和 hash；
- 不切换 BarReader 默认读取。

当前已实现 Slice 1a/1b：`dataset_manifest.py` 提供 canonical JSON、volatile timestamp 排除、manifest SHA-256、partition URI/row count/checksum 结构校验和 immutable manifest 文件写入；`dataset_versions` 与 `dataset_version_partitions` 已提供 candidate 元数据、稳定内容去重和 sealed partition 登记。repository 已强制 `candidate → ready → published` 质量状态门禁以及 candidate/ready → rejected；Snapshot 已能只引用 published version，并用 `draft → active → retired` 和 active partial unique index 固定单用户研究输入。尚未接入 partition materialization、snapshot-bound BarReader 或离线回测。

验收：重复输入 hash 稳定、任一字节改变校验失败、row count 求和一致、无绝对路径。

### Slice 2：quality gate + publish

- quality 绑定 version/partitions；
- internal publisher 实现合法状态迁移；
- error 拒绝、warning 留痕、重复 publish 幂等、旧 active 不变。

### Slice 3：snapshot + active pointer

- 增加 snapshot/member 与 `active_snapshot_id`；
- 仅 published version 可引用；
- 双 session 并发激活测试；
- active 切换失败保持旧指针。

### Slice 4：snapshot-bound BarReader

- `resolve(snapshot_id)`；
- 按 manifest 固定 partition 读取；
- checksum/缺文件 fail closed；
- 新发布后旧 snapshot 结果不变。

### Slice 5：最小 BacktestRun

只有 Slice 4 稳定后实现：

```text
snapshot_id
strategy_code/version
parameters
calendar/version
adjust_type
fee/slippage/rule profiles
engine_version
result_sha256
```

禁止 provider 调用和 canonical 写入；同一输入重复运行结果 checksum 必须一致。

## 8. PostgreSQL / SQLite 测试分层

- PR 快速层：纯单元 + SQLite fresh/legacy + migration round-trip；
- 数据层：DuckDB/Parquet、manifest checksum、publish failure injection、snapshot immutability；
- PostgreSQL 集成层：真实 PostgreSQL migration、局部索引 predicate、FK RESTRICT、并发发布/并发 replay；
- nightly：崩溃点注入、orphan/reconcile、旧 snapshot 重放。

不引入 Kafka、Airflow、Celery、Redis、Iceberg/Delta 或微服务拆分；先用 SQL 元数据 + immutable Parquet + governed reader 完成闭环。

## 9. 参考依据

- 本地知识库：`developer-roadmap` 的 DVC、MLOps、data lineage、metadata-first、Delta Lake、MVCC、backup validation 条目；仅提取原则，不照搬平台。
- OSkhQuant 固定版本研究结论：只借鉴成本模型、T+1/T+0 和结果留档原则，不复制 MiniQMT、GUI 或交易耦合；关键取舍已写入本规格，原始研究记录由 Git 历史保留。
