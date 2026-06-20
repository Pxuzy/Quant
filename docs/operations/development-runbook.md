# 开发运行手册

## 环境位置

当前仓库根目录是 `E:\hermes\workspace\Quant`。

Python 运行材料位于：

- `quant/requirements.txt`
- `quant/.env.example`
- `quant/scripts/run_api_server.py`
- `quant/docker-compose.yml`

前端运行材料位于：

- `apps/web/package.json`
- `apps/web/vite.config.ts`

## 关键环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `Quant API` | FastAPI 应用名称 |
| `APP_ENV` | `local` | 运行环境 |
| `DATABASE_URL` | `sqlite:///./storage/quant.db` | 元数据库连接 |
| `DATA_LAKE_DIR` | `./storage/lake` | Parquet 数据湖路径 |
| `CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | CORS 白名单 |
| `TUSHARE_TOKEN` | 空 | Tushare 可选凭证 |
| `STOCK_SDK_CWD` | 空 | Stock SDK 可选 Node 包目录 |

## 启动 PostgreSQL

在 `quant` 目录运行：

```powershell
docker compose up -d postgres
```

本地快速启动可以继续使用 SQLite fallback。

## 一键启动本地工作台

推荐从仓库根目录使用开发生命周期脚本：

```powershell
.\scripts\quant-dev.cmd start-bg
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd smoke
```

默认地址：

- API: `http://127.0.0.1:8021/health`
- Web: `http://127.0.0.1:5175/data-system/overview`

`status` / `smoke` 不只检查 Web HTML 200，还会检查 Vite 入口模块 `/src/main.tsx`。如果入口模块返回 Vite error overlay，脚本会把 Web 判定为未就绪，避免“页面 200 但 React 根节点为空”的白屏假阳性。

常用管理命令：

```powershell
.\scripts\quant-dev.cmd logs
.\scripts\quant-dev.cmd stop
```

脚本会显示 API/Web 的端口 owner、托管 pid 文件和日志位置。若端口已被旧进程占用，默认只报告不误杀；确需停止端口 owner 时，可在 PowerShell 中显式添加 `-ForcePortOwner`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\quant-dev.ps1 stop -ForcePortOwner
```

前端 npm 脚本已预加载一个很窄的 Windows Vite 兼容 shim，用于避开 Vite `net use` 探测触发的 `spawn EPERM`。如果仍在 esbuild 或其他 Node helper 阶段出现 `spawn EPERM`，优先检查 Windows 安全软件、受控文件夹访问或 Node 安装环境；这通常不是前端路由或 API 代理配置问题。

## 启动 API

在 `quant` 目录运行前台服务：

```powershell
.\.venv\Scripts\python.exe scripts\run_api_server.py run
```

后台服务：

```powershell
.\.venv\Scripts\python.exe scripts\run_api_server.py start
.\.venv\Scripts\python.exe scripts\run_api_server.py status
.\.venv\Scripts\python.exe scripts\run_api_server.py stop
```

默认 API 端口以脚本配置为准；前端代理默认指向本地 API。

## 启动前端

在 `apps/web` 目录运行：

```powershell
npm run dev
```

构建和类型检查：

```powershell
npm run type-check
npm run build
```

## Worker 命令

Worker 入口是 `apps/worker/sync_stocks.py`。

查看支持参数：

```powershell
python -m apps.worker.sync_stocks --help
```

执行股票池同步：

```powershell
python -m apps.worker.sync_stocks --task-type stock_list --source auto --market A_SHARE
```

创建单股日线同步：

```powershell
python -m apps.worker.sync_stocks --task-type daily_bars --source auto --market A_SHARE --symbol 600519 --start-date 2024-01-01 --end-date 2024-12-31
```

创建市场级日线缺口补齐：

```powershell
python -m apps.worker.sync_stocks --task-type daily_bars_market_repair --source auto --market A_SHARE --start-date 2024-01-01 --end-date 2024-01-31 --max-symbols 20
```

执行最早的 pending 任务：

```powershell
python -m apps.worker.sync_stocks --run-next-pending
```

## 测试

后端和 worker 测试位于 `tests/api` 和 `tests/worker`。

常用命令：

```powershell
pytest tests/api
pytest tests/worker
```

前端验证：

```powershell
cd apps\web
npm run type-check
npm run build
```

## 发布前检查

- API 测试通过。
- Worker 测试通过。
- 前端类型检查通过。
- 前端构建通过。
- 新增 API 已更新 [API 目录](../architecture/api-catalog.md)。
- 新增页面或入口已更新 [功能矩阵](../product/feature-catalog.md)。
- 新增任务、数据源或数据集已更新 [数据源和同步治理](../data/data-source-and-sync-governance.md)。
