# Quant

Quant is a modular quantitative trading data platform. The first build focuses on the stock data management foundation: stock basics, data-source configuration, sync tasks, and a React management UI.

## First Milestone

The first milestone is a real stock data loop:

```text
data source -> normalize -> metadata database / Parquet lake -> API -> frontend workbench
```

It deliberately does not include strategy, backtesting, Redis, MongoDB, or real-time trading. Those modules should depend on the data-system contracts after the foundation is stable.

## Planned Stack

- Backend: FastAPI + SQLAlchemy
- Database: SQLite fallback for local bootstrap, PostgreSQL for the main path
- Worker: lightweight Python worker entry point
- Frontend: React + Vite + TypeScript + Ant Design + TanStack Query
- Data lake: Parquet for market data; DuckDB for fast local analytical queries

## Data Sources

The first provider set is:

- AKShare: public-data Python package, enabled by default for stock basics.
- BaoStock: free A-share Python package, enabled by default for stock basics and daily bars.
- AData: public-data Python package, enabled by default for stock basics and daily bars.
- Tushare: professional Python package, disabled by default until `TUSHARE_TOKEN` is configured.
- Stock SDK: community Node package, declared in `apps/web/package.json` and disabled by default until the source is explicitly enabled.

The product registry intentionally exposes only these named providers in the first version. Test fake adapters may exist inside tests, but they must not appear in the runtime provider list.

Data-source settings live inside the data-system area. Generic system settings should not store provider credentials, provider priority, or provider health state.

## Local Database

Start PostgreSQL when you want to use the main database path:

```powershell
docker compose up -d postgres
```

For quick local bootstrap, the backend defaults to:

```text
sqlite:///./storage/quant.db
```

## Environment

Copy `.env.example` to `.env` and adjust values as needed. Optional provider packages and credentials are enabled per source; tests use local fake adapters instead of external network calls.

The local virtual environment should install the Python packages in `requirements.txt`. Tushare is installed as a supported provider package, but the Tushare source stays disabled until `TUSHARE_TOKEN` is configured and the source is explicitly enabled in the data-system area.

Stock SDK is optional at runtime because it runs through Node.js. The package is declared in the frontend app, so `npm install` in `apps/web` is enough for the default setup. Set `STOCK_SDK_CWD` only when you want the backend to load `stock-sdk` from another directory:

```powershell
cd ..\apps\web
npm install
```

## Local Services

From the workspace root, the simplest development entrypoint is:

```powershell
.\scripts\quant-dev.cmd start-bg
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd smoke
```

This starts or verifies the API on `http://127.0.0.1:8021` and the web workbench on `http://127.0.0.1:5175`. It also reports port owners and log paths so stale local processes are visible.

The Web readiness check verifies both the routed HTML page and the Vite entry module (`/src/main.tsx`). A Vite module 500 is reported as Web not ready instead of a blank React root.

Use these when diagnosing a local run:

```powershell
.\scripts\quant-dev.cmd logs
.\scripts\quant-dev.cmd stop
```

If an unmanaged process already owns a port and you intentionally want the script to stop it, add `-ForcePortOwner` from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\quant-dev.ps1 stop -ForcePortOwner
```

Frontend npm scripts preload a narrow Windows Vite compatibility shim for the `net use` probe that can trigger `spawn EPERM`. If Vite still fails while starting esbuild or another Node helper, the likely cause is Windows security software or a broken Node environment blocking helper process creation, not a Quant route or API issue.

Start the API in the foreground:

```powershell
.\.venv\Scripts\python.exe scripts\run_api_server.py run
```

Start, check, and stop the API in the background:

```powershell
.\.venv\Scripts\python.exe scripts\run_api_server.py start
.\.venv\Scripts\python.exe scripts\run_api_server.py status
.\.venv\Scripts\python.exe scripts\run_api_server.py stop
```

The frontend dev server runs on `http://127.0.0.1:5174` and proxies `/api` to `http://127.0.0.1:8021` by default.

If you need different local ports, set these before starting the API and frontend:

```powershell
$env:QUANT_API_PORT="8022"
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8022"
$env:VITE_DEV_SERVER_PORT="5175"
```

## Architecture

See [stock-data-system-design.md](docs/architecture/stock-data-system-design.md).

For the current product-level target and five-entry workbench structure, see [stock-database-workbench.md](docs/architecture/stock-database-workbench.md).
