# 本地 A 股日线研究数据库设计

> 状态：已确认，待实施
>
> 适用用户：单用户、本地优先的 A 股研究与离线回测使用者。
>
> 与 KHQuant 的关系：借鉴其“先补充本地历史数据，再离线高速回测”的使用体验；不复制其 MiniQMT、`xtquant`、`userdata_mini/datadir` 或私有 `.dat` 存储。

## 1. 问题与目标

当前 Quant 已具备股票池、日线同步、raw artifact、ingest batch、质量、Parquet、DuckDB、DatasetVersion、Manifest 和 Snapshot 基础，但尚未形成一个用户可直接初始化、每日维护和用于可复现回测的本地数据库产品闭环。

本设计建设一个本地 A 股日线研究数据库，满足：

1. 覆盖全 A 股近 5 年日线；
2. 同时保存不复权、前复权、后复权三套已物化价格；
3. 每个交易日收盘后自动增量；
4. 页面支持初始化、补数、重跑、进度、失败、覆盖和质量查看；
5. 研究和回测离线读取，不在运行期间请求 provider；
6. 每次回测绑定不可变 Snapshot，能够重复读取相同输入；
7. 更新失败时继续保留旧 active Snapshot，不污染已发布数据。

## 2. 已确认范围

### 2.1 第一版包含

- 市场：A 股，含 SSE、SZSE、BSE；
- 股票范围：全部当前和近 5 年内曾上市的 A 股证券；
- 历史窗口：滚动近 5 年到最新交易日；
- 频率：日线；
- 复权口径：`none`、`qfq`、`hfq` 三套均物化保存；
- 数据字段：OHLCV、成交额、前收盘、复权因子、来源和入库时间；
- 数据操作：首次初始化、每日增量、指定股票补数、指定日期补数、指定口径重跑、raw replay；
- 数据治理：raw artifact、schema validation、ingest batch、质量检查、Manifest、DatasetVersion、Snapshot；
- 用户入口：页面与后台调度；
- 消费方式：BarReader 与后续离线回测。

### 2.2 第一版不包含

- 分钟线、Tick、order book 和实时流；
- 财务报表、估值、行业、新闻和因子；
- 实盘交易、Broker、MiniQMT 和 `xtquant`；
- 多用户、复杂权限和云端分布式部署；
- Kafka、Airflow、Celery、Redis、Iceberg 和 Delta Lake；
- 完整策略市场或完整回测平台。

## 3. KHQuant 参考边界

固定提交 `7228f55741b445cb25116683e5753f82a5422825` 的源码和 README 表明：

- “数据补充”调用 `xtquant.download_history_data()`，写入 MiniQMT 的 `userdata_mini/datadir`；
- MiniQMT 使用按市场与周期组织的内部 `.dat` 二进制数据；
- 回测通过 `get_market_data_ex()` / `get_local_data()` 读取本地数据；
- “数据下载”另行导出 CSV，供 Excel、Python、R 和外部研究使用。

Quant 只借鉴以下原则：

- 回测前先完成本地数据补充；
- 内部读取和外部导出有清晰边界；
- 长任务后台执行并显示进度；
- 数据缺失必须显式提示，不能假装回测输入完整。

Quant 不采用 MiniQMT 私有数据格式和运行时耦合，而使用开放、可校验、可迁移的 SQLite/PostgreSQL + Parquet + DuckDB。

## 4. 总体架构

```text
AKShare / BaoStock / Stock SDK
              │
              ▼
  初始化 / 每日增量 / 手动补数任务
              │
              ▼
       immutable raw artifact
              │
              ▼
 normalize + schema validation
              │
              ▼
        ingest batch / quality
              │
              ▼
 immutable partition materialization
 none + qfq + hfq（分开发布）
              │
              ▼
 DatasetVersion + canonical Manifest
              │
              ▼
      quality gate + publish
              │
              ▼
       active Snapshot pointer
              │
              ▼
 snapshot-bound BarReader / 回测
```

### 4.1 存储职责

| 存储 | 职责 | 权威性 |
| --- | --- | --- |
| SQLite | 本地默认元数据库；任务、批次、质量、版本、快照、调度 | 单机元数据权威 |
| PostgreSQL | 可选生产元数据库；与 SQLite 使用相同 Alembic schema | 多进程元数据权威 |
| Parquet | 三套日线的不可变 version partitions | 行情数据权威 |
| DuckDB | 扫描 Parquet、筛选、聚合和列投影 | 可重建查询引擎 |
| Raw artifact | Provider 原始响应和 checksum | 重放与审计依据 |
| Manifest JSON | partition、checksum、行数、范围和 lineage | 版本内容身份 |

SQLite 与 PostgreSQL 只存元数据和轻量业务表，不把全量 OHLCV 复制为关系型大表。

## 5. 数据集与物理分区

### 5.1 逻辑数据集

第一版只发布一个逻辑数据集 `daily_bars`。每个 DatasetVersion 只能声明一个 `adjust_type`，因此一次完整日更至少产生三个候选版本：

```text
daily_bars / none
daily_bars / qfq
daily_bars / hfq
```

Snapshot 同时固定三套 published version。调用方必须明确口径，禁止在一个读取结果内混合。

### 5.2 日线唯一身份

```text
(symbol, exchange, market, trade_date, adjust_type)
```

其中：

- `symbol` 使用纯数字代码；
- `exchange` 为 `SSE`、`SZSE`、`BSE`；
- `market` 第一版固定为 `A_SHARE`；
- `trade_date` 是 `Asia/Shanghai` 的交易日日期；
- `adjust_type` 为 `none`、`qfq`、`hfq`。

### 5.3 推荐分区

```text
versions/daily_bars/<version-key>/
  adjust_type=none/trade_year=2022/part-*.parquet
  adjust_type=qfq/trade_year=2022/part-*.parquet
  adjust_type=hfq/trade_year=2022/part-*.parquet
```

约束：

- version 路径只写一次；
- 已 sealed 文件不得覆盖；
- partition URI 必须相对 lake root；
- 不按单股票或单交易日生成海量小文件；
- 每个 partition 在 Manifest 中记录 SHA-256、字节数、行数、最小/最大日期和 batch lineage。

### 5.4 三套复权口径

用户已明确要求三套物化数据。系统必须保证：

- 三套数据分别进入版本身份；
- 前后复权价格和成交量口径由 adapter 契约记录；
- 不允许只改 `adjust_type` 标签伪造复权；
- provider 不提供可靠复权口径时，该口径 candidate 失败，不从其他口径复制；
- 同一 Snapshot 中三套版本使用相同股票范围和交易窗口；
- 每日质量报告比较三套覆盖，不强制价格相同。

## 6. 历史窗口与增量语义

### 6.1 首次初始化

初始化目标日期为：

```text
[max(当前日期 - 5年, 股票上市日期), 最新已完成交易日]
```

步骤：

1. 更新股票池和退市状态；
2. 获取交易日历；
3. 为每只证券计算有效交易窗口；
4. 按 provider、股票批次、复权口径和日期范围创建任务；
5. 写 raw artifact、normalize、validate、batch；
6. 物化三个 candidate version；
7. 运行质量门禁；
8. 三个版本均 ready 后发布并激活 Snapshot。

初始化允许分批执行和断点恢复，不要求一次进程完成全部证券。

### 6.2 每日自动增量

默认调度口径：

- 仅交易日执行；
- `Asia/Shanghai` 15:30 后开始；
- 目标结束日期为最新已完成交易日；
- 先更新股票池和交易日历，再更新三套日线；
- 默认只拉 watermark 之后的缺失交易日；
- 当天无新数据时任务成功且 `records_written=0`；
- 发布失败时旧 Snapshot 保持 active。

调度时间必须可配置，但第一版不引入外部调度系统，沿用 `sync_schedules + lightweight worker`。

### 6.3 滚动 5 年窗口

每日发布时，新的 DatasetVersion 只声明最近 5 年窗口；旧 Snapshot 仍可引用其原有窗口。历史 partition 清理必须满足：

- 未被任何 Snapshot 引用；
- 不属于 active/published version；
- 超过可配置保留期；
- 清理前生成预览和审计记录。

第一版只实现清理预览，不自动删除历史版本文件。

## 7. 状态机与原子发布

### 7.1 DatasetVersion

```text
candidate -> ready -> published -> retired
    │           │
    └-> rejected└-> rejected
```

发布条件：

- Manifest 文件存在且 checksum 匹配；
- 所有 partitions 为 `sealed`；
- partition row count 总和等于 version row count；
- schema、normalize 和 adjust type 单一；
- 质量无 error；
- warning 已写入 Manifest；
- 日期范围和股票覆盖满足策略。

published/retired 不允许回退或修改内容。

### 7.2 Snapshot

```text
draft -> active -> retired
```

Snapshot members 至少包括：

```text
role=bars-none -> published none version
role=bars-qfq  -> published qfq version
role=bars-hfq  -> published hfq version
role=calendar  -> published calendar version（后续切片）
role=universe  -> published stock-universe version（后续切片）
```

激活事务：

1. 校验 draft 和 members；
2. 锁定当前 active；
3. 将旧 active 标记 retired；
4. 将新 snapshot 标记 active；
5. commit。

失败时整个 SQL 指针事务回滚，旧 active 不变。文件系统不参与该事务。

## 8. 质量门禁

### 8.1 硬失败

- raw checksum/字节数/envelope 不一致；
- schema 不兼容；
- 主键重复；
- `raw_records > 0` 且 `normalized_records == 0`；
- OHLC 关系错误；
- 负成交量或非法日期；
- partition 文件缺失或 checksum 不匹配；
- Manifest 行数不等于 partition 总和；
- 三套版本股票范围或交易范围不一致；
- error 级质量报告。

### 8.2 Warning

- 单个 provider 不可用但已成功 fallback；
- 个别停牌证券在交易日无记录；
- 新上市证券不足 5 年；
- 退市证券的窗口提前结束；
- 部分 raw 记录被丢弃但未超过策略阈值；
- 当天全市场数据在配置的延迟窗口内尚未齐全。

Warning 可发布，但必须出现在 DatasetVersion、Manifest、质量报告和页面上。

## 9. Provider 策略

第一版候选来源：

```text
akshare
baostock
stock_sdk
```

要求：

- 正式初始化前必须至少有一个启用且 smoke test 通过的日线 provider；
- auto 模式按能力、健康和历史成功率排序；
- 每个 batch 记录 requested source 和实际 source；
- 单 provider 失败可 fallback；
- 失败位置和尝试顺序写任务日志；
- 大规模初始化要有限流、超时、重试和指数退避；
- provider 不可用不能产生“成功但空”的 published version。

当前运行环境中的 AKShare/BaoStock 依赖缺失、Stock SDK 健康但禁用，是实施前必须解决的环境门禁。

## 10. 页面与操作

在现有数据可信后台中新增“本地行情库”能力，不创建第二套孤立后台。

### 10.1 概览

显示：

- 股票总数；
- none/qfq/hfq 行数和覆盖；
- 最早/最新交易日；
- 当前 active Snapshot；
- 最近成功发布时间；
- 今日进度、失败数、质量异常数；
- Parquet、raw artifact 和元数据库磁盘占用；
- 当前启用 provider 及健康状态。

### 10.2 覆盖矩阵

每只股票显示：

- 上市/退市日期；
- 三种口径的最早/最新日期；
- 缺失交易日数量；
- 最新入库 batch；
- 来源；
- 质量状态；
- 补数入口。

### 10.3 操作入口

- 初始化近 5 年数据库；
- 每日增量；
- 指定股票补数；
- 指定日期范围补数；
- 指定复权口径重跑；
- raw artifact replay；
- 预览候选版本；
- 发布并激活 Snapshot；
- 查看和比较历史 Snapshot；
- 导出当前查询结果为 CSV。

CSV 是外部研究导出，不是内部回测权威输入。

## 11. API 边界

### 11.1 管理接口

```text
GET  /api/local-market-db/overview
GET  /api/local-market-db/coverage
POST /api/local-market-db/initialize
POST /api/local-market-db/increment
POST /api/local-market-db/repair
POST /api/local-market-db/replay
GET  /api/datasets/daily_bars/versions
GET  /api/datasets/daily_bars/versions/{id}
GET  /api/datasets/daily_bars/versions/{id}/manifest
GET  /api/snapshots
GET  /api/snapshots/{id}
POST /api/snapshots/{id}/activate
```

所有写操作只创建任务或执行受控状态迁移，不在 HTTP 请求内同步抓取全市场数据。

### 11.2 研究读取

```text
GET /api/research-data/bars
```

增量参数：

```text
snapshot_id
symbols[]
adjust_type
start_date
end_date
fields[]
page/page_size
```

规则：

- 回测必须显式传 `snapshot_id`；
- 交互查询可默认 active，但响应必须返回实际 snapshot ID；
- 请求开始时解析一次 Snapshot；
- 分页不得重新解析 latest/active；
- 文件缺失或 checksum 失败时 fail closed；
- 禁止回退到 mutable DuckDB latest 或 provider。

## 12. 失败补偿与运维

| 失败点 | 状态与补偿 |
| --- | --- |
| provider fetch 失败 | 尝试 fallback；全部失败则 task/batch failed |
| raw 写入失败 | 不进入 normalize；task failed |
| normalize/schema 失败 | batch failed；raw 保留用于 replay |
| DuckDB 已写、Parquet 失败 | `reconcile_required`；不发布 |
| candidate partition 失败 | version failed/rejected；旧 active 不变 |
| Manifest 已写、SQL 登记失败 | orphan manifest；reconcile 扫描 |
| quality error | candidate rejected；旧 active 不变 |
| version published、Snapshot 激活失败 | version 保持 published，可重试激活 |
| BarReader 文件损坏 | 请求失败并告警，不读其他版本 |

运维页面必须可根据 task、batch、raw artifact、version 和 Snapshot 逐层定位失败。

## 13. 性能与容量

全 A 股近 5 年约为数百万到千万级日线记录；三套物化后仍适合单机 Parquet + DuckDB。第一版约束：

- API 列表全部分页；
- BarReader 执行列投影和日期/股票谓词下推；
- 初始化按有限批次并发，不一次加载全市场到内存；
- 合并小文件时生成新 immutable version，不覆盖旧文件；
- DuckDB 连接按 lake/database 隔离；
- 页面不轮询大表，只轮询任务和聚合状态；
- 不把三个复权口径再复制到 PostgreSQL。

磁盘阈值、初始化估算和实际占用必须在首次运行前后展示，但不在规格中假定固定压缩比。

## 14. 安全与数据边界

- 所有文件路径必须解析并限制在配置的 lake/raw root 内；
- API 不返回主机绝对路径；
- Manifest 只存相对 URI；
- Provider 返回的数据视为不可信输入；
- 错误日志隐藏 token、代理凭据和完整外部 URL 参数；
- CSV 导出防止公式注入；
- 删除/清理必须预览并有审计，不提供无确认的递归删除；
- Snapshot 和 published version 默认不可删除。

## 15. 验收标准

### 15.1 数据正确性

- [ ] 全 A 股股票池和交易日历入库；
- [ ] 近 5 年有效交易窗口计算正确；
- [ ] none/qfq/hfq 三套日线均有独立版本和 Manifest；
- [ ] 日线唯一键包含 `adjust_type`；
- [ ] 重复同步实际新增行数为 0；
- [ ] 缺口补齐只抓缺失日期；
- [ ] provider fallback 记录实际来源；
- [ ] 三套版本覆盖范围一致；
- [ ] Manifest checksum、文件、行数和日期范围一致；
- [ ] error 质量结果阻断发布。

### 15.2 可复现性

- [ ] 回测保存明确 Snapshot ID；
- [ ] 同一 Snapshot 多次读取 checksum 和行数一致；
- [ ] 发布新 Snapshot 后旧 Snapshot 读取不变；
- [ ] 无网络时可读取 published Snapshot；
- [ ] BarReader 不访问 provider；
- [ ] 文件损坏时 fail closed。

### 15.3 调度与恢复

- [ ] 交易日收盘后自动创建增量任务；
- [ ] 非交易日不创建行情任务；
- [ ] 初始化可断点恢复；
- [ ] 单只股票失败不丢失其他成功审计；
- [ ] raw replay 不重新访问 provider；
- [ ] 发布或激活失败时旧 active 保持不变；
- [ ] 页面显示进度、失败、覆盖、质量和磁盘占用。

### 15.4 工程门禁

- [ ] SQLite fresh/legacy migration round-trip；
- [ ] PostgreSQL 真实 migration 和并发发布测试；
- [ ] DuckDB/PyArrow 查询一致；
- [ ] backend/worker 全量测试通过；
- [ ] TypeScript type-check 和生产构建通过；
- [ ] 小规模真实数据 smoke：3 只股票、30 个交易日、3 个复权口径；
- [ ] 扩展 smoke：不少于 100 只股票；
- [ ] 初始化前有磁盘空间预估，完成后有实际占用报告。

## 16. 实施切片

1. **环境门禁**：安装/启用至少一个正式日线 provider，并完成 3 股票 smoke；
2. **本地数据库范围模型**：滚动 5 年策略、三套复权覆盖计算和初始化计划；
3. **Immutable materialization**：从 governed 数据生成 version partitions 与 Manifest；
4. **Quality publish**：candidate、质量门禁、三口径一致性和 published 状态；
5. **Snapshot 激活**：三套 version 固定到单一 Snapshot，原子切换 active；
6. **Snapshot-bound BarReader**：按 Manifest 读取并 fail closed；
7. **每日增量调度**：交易日判断、15:30 后调度、watermark 和重试；
8. **本地行情库页面**：概览、覆盖、初始化、增量、补数、失败和 Snapshot；
9. **CSV 导出**：只导出受控查询结果；
10. **真实全量初始化**：先 100 股票，再全 A 股，记录耗时、失败和磁盘占用。

每个切片必须独立通过 TDD、迁移和只读审查后再进入下一切片。

## 17. 文件影响图

预计新增：

```text
backend/app/services/local_market_database_service.py
backend/app/services/dataset_materialization_service.py
backend/app/repositories/snapshots.py（已有基础，继续完善）
backend/app/routers/local_market_database.py
backend/app/schemas/local_market_database.py
frontend/src/features/local-market-database/
frontend/src/pages/data-system/local-market-database/
tests/api/test_local_market_database.py
tests/api/test_dataset_materialization.py
tests/worker/test_daily_increment_schedule.py
```

预计修改：

```text
backend/app/models/entities.py
backend/app/repositories/daily_bars.py
backend/app/repositories/dataset_versions.py
backend/app/services/research_data_service.py
backend/app/routers/research_data.py
backend/worker/sync_stocks.py
frontend/src/app/router.tsx
frontend/src/layouts/AppLayout.tsx
docs/architecture/data-model.md
docs/data/lifecycle.md
docs/status/roadmap.md
```

实际实施以每个切片开始时的最新代码为准，不提前修改无关模块。

## 18. 已知约束与决策

- 三套复权是用户明确要求，接受约 3 倍逻辑数据量；
- 第一版只做全 A 股近 5 年日线；
- 每日自动增量并保留页面一键补数/重跑；
- 回测必须使用 Snapshot；
- 元数据库默认 SQLite、兼容 PostgreSQL；
- Parquet 是日线权威文件，DuckDB 是查询引擎；
- CSV 仅用于外部导出；
- 不兼容 MiniQMT `.dat`，不引入 `xtquant`；
- 分钟线、财务、新闻、因子和实盘交易后置。
