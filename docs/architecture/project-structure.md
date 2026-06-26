# 项目结构边界

Quant 保持模块化单体结构，不照搬单应用模板。目录按运行边界和职责划分，而不是按“看起来完整”拆层。

## 顶层目录

| 路径 | 职责 | 约束 |
| --- | --- | --- |
| `apps/api` | FastAPI 后端业务代码 | 新增 API、业务服务、仓储、schema、model、adapter 放这里 |
| `apps/web` | React 前端工作台 | 只调用后端 API，不直接访问 provider、数据库或 Parquet 路径 |
| `apps/worker` | 后台同步入口 | 保留 CLI 和任务执行入口，复用 `apps/api` 的服务层 |
| `scripts` | 本地开发生命周期脚本 | 启动、状态、验证、辅助开发命令 |
| `quant` | 运行材料和兼容层 | 依赖、环境样例、Docker、launcher；不再新增业务逻辑 |
| `tests` | API 和 worker 测试 | 按被测运行边界分组 |
| `docs` | 产品、架构、运行手册 | 行为、API、数据模型或目录边界变化后同步更新 |

## 后端业务边界

`apps/api` 是后端业务代码主目录：

```text
apps/api/
  main.py          FastAPI app factory and router registration
  core/            config, compatibility, shared backend utilities
  db/              SQLAlchemy engine/session/base
  models/          SQLAlchemy entities
  schemas/         Pydantic request/response models
  routers/         HTTP API boundary
  services/        business orchestration
  repositories/    database persistence
  adapters/        external data providers
```

推荐依赖方向：

```text
routers -> services -> repositories -> models/db
                 \-> adapters
```

反向依赖不允许。前端和 worker 可以调用 API contract 或服务入口，但不应绕过服务层直接拼第三方 provider、SQLite、DuckDB 或 Parquet 路径。

## `quant` 目录定位

`quant` 目录保留为本地运行材料和兼容层：

- `quant/scripts/run_api_server.py` 负责本地 API launcher。
- `quant/requirements.txt`、`quant/.env.example`、`quant/docker-compose.yml` 仍描述 Python 运行环境。
- `quant/services/*` 只保留旧 import 的兼容导出；新业务服务放到 `apps/api/services`。

## 第一阶段整理原则

- 不做大规模搬家。
- 每次只移动一个清晰边界。
- 旧 import 先保留兼容层，再用测试证明新旧路径一致。
- 临时文件、缓存、生成物不作为业务结构的一部分。
- 代码移动必须配套测试、文档和运行验证。
