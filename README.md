# Quant

Local-first A 股量化研究工作台。管理数据源、同步行情、检查质量，并通过 Web 界面研究股票。

---

## 🚀 快速开始（Docker）

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f

# 打开工作台
# http://localhost:8000
```

所有数据持久化在 Docker volume `quant-data` 中，重启不丢失。

---

## 🛠️ 本地开发

### 后端

```bash
# Python 3.11+
pip install -e ".[dev,adapters]"

# 启动 API 服务
uvicorn backend.app.main:app --reload --port 8000

# 运行测试
pytest
```

### 前端

```bash
cd frontend
npm install
npm run dev    # 开发模式，端口 5173
npm run build  # 构建生产版本
```

构建后访问 `http://localhost:8000`（后端自动托管前端）。

### Worker（同步任务）

```bash
# 执行下一条待处理任务
python -m backend.worker.sync_stocks --run-next-pending
```

---

## 📖 功能总览

| 页面 | 路径 | 功能 |
|------|------|------|
| **总控台** | `/dashboard` | 大盘指数、自选股行情、新闻概览 |
| **股票池** | `/stocks` | A 股全量股票查询、筛选、同步 |
| **股票详情** | `/stocks/{symbol}` | K 线图、行情、覆盖率和质量 |
| **新闻** | `/news` | 财经新闻聚合、分类 |
| **数据源** | `/data-sources` | Provider 注册、健康检查、smoke test |
| **同步任务** | `/sync-tasks` | 同步调度、任务管理、修复 |
| **数据库** | `/database` | 存储状态、覆盖率、血缘、质量 |
| **数值数据** | `/numeric-summary` | 标准化数据浏览 |
| **管线** | `/pipeline` | 数据管线状态 |
| **告警** | `/alerts` | 系统告警 |
| **数据集** | `/api/datasets` | 数据集目录 |

---

## 🐳 部署架构

```
┌─────────────┐     ┌──────────────────────────────────────┐
│  浏览器      │────▶│  Docker Container                    │
│ localhost    │     │  ┌────────┐  ┌────────────────────┐  │
└─────────────┘     │  │ FastAPI │  │ React SPA (built)  │  │
                    │  │ :8000  │  │ frontend/dist/     │  │
                    │  └────┬───┘  └────────────────────┘  │
                    │       │                              │
                    │  ┌────▼───────────────────────────┐  │
                    │  │ SQLite / Parquet / DuckDB      │  │
                    │  │ Volume: /data                  │  │
                    │  └────────────────────────────────┘  │
                    └──────────────────────────────────────┘
```

---

## ⚙️ 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///./storage/quant.db` | 元数据库 |
| `DATA_LAKE_DIR` | `./storage/lake` | Parquet 数据湖路径 |
| `DUCKDB_PATH` | `{DATA_LAKE_DIR}/quant.duckdb` | DuckDB 查询引擎路径 |
| `CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 允许的跨域来源 |
| `APP_ENV` | `local` | 运行环境 |

---

## 📚 文档

- [完整架构说明](./docs/architecture/ARCHITECTURE.md) — 模块分层、每文件功能
- [数据生命周期](./docs/data/lifecycle.md) — 从数据源到消费的全链路
- [开发手册](./docs/operations/development-runbook.md) — 本地运行细节
- [API 目录](./docs/architecture/api-catalog.md) — 所有端点

---

## ✅ 测试

```bash
# 全量测试
pytest

# 指定模块
pytest tests/api/
pytest tests/worker/
```

---

## 📜 许可

MIT
