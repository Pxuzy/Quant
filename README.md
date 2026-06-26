# Quant

Quant is a local-first personal stock research workbench. It uses a stock data management layer to support daily research workflows: watch stocks, inspect price data, read related news, and check whether the local data is fresh and trustworthy.

The current phase focuses on A-share data. It keeps the existing FastAPI + React + local metadata database + Parquet lake architecture, but the product direction is no longer “a database page with many tables”. The intended shape is:

- a stock research workspace for daily use;
- a data trust backoffice for provider health, sync tasks, quality, lineage, and repair;
- a stable data foundation for later factor research, backtesting, strategy, portfolio, risk, and trading modules.

Phase 1 does not implement live trading, a full backtesting engine, a plugin marketplace, or a mobile workflow.

## Backtesting And AI Direction

Backtesting and AI research are planned as downstream consumers of the data foundation, not parallel data pipelines.

The intended order is:

1. stabilize A-share stock, daily bar, calendar, news, quality, lineage, and dataset contracts;
2. expose a small research data access layer, such as a `BarReader` or `DataPortal`, over API responses or silver/gold datasets;
3. build factor, backtest, AI assistant, portfolio, and strategy modules on top of that access layer.

These future modules must not call third-party providers directly, open SQLite/PostgreSQL tables directly, or construct Parquet paths in UI or research code. If a research workflow needs new data, add it to the governed ingest path first.

## Documentation

Start from the documentation center:

- [docs/INDEX.md](./docs/INDEX.md)

Recommended reading order:

1. [Project overview](./docs/overview/project-overview.md)
2. [Personal stock workbench direction](./docs/product/personal-stock-workbench.md)
3. [Phase 1 product baseline](./docs/product/phase-1-baseline.md)
4. [Feature catalog](./docs/product/feature-catalog.md)
5. [System architecture](./docs/architecture/system-overview.md)
6. [Development runbook](./docs/operations/development-runbook.md)
7. [Roadmap and status](./docs/status/roadmap.md)

## Current Stack

| Layer | Stack |
| --- | --- |
| Frontend | React, Vite, TypeScript, Ant Design, ProComponents, TanStack Router, TanStack Query |
| API | FastAPI, SQLAlchemy |
| Metadata database | SQLite fallback, PostgreSQL main path |
| Data lake | Parquet |
| Query engine | DuckDB |
| Worker | Lightweight Python worker |
| Data sources | AKShare, BaoStock, AData, Tushare, Stock SDK |

## Product Entrypoints

The web workbench is organized into two product layers.

| Layer | Entrypoints |
| --- | --- |
| Stock research workspace | 总控台、股票池、股票详情、新闻汇总、数值数据 |
| Data trust backoffice | 数据源管理、同步调度、数据库管理 |

Legacy detail routes for market data, datasets, trading calendars, and data quality are redirected or folded into stock detail and database management.

## Local Runtime

Runtime details live in [quant/README.md](./quant/README.md) and [development-runbook.md](./docs/operations/development-runbook.md).

Recommended root-level lifecycle commands:

```powershell
.\scripts\quant-dev.cmd start-bg
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd smoke
```

Open the workbench at `http://127.0.0.1:5175/data-system/overview`.

The lifecycle smoke check verifies both the routed HTML page and the Vite entry module (`/src/main.tsx`), so a Vite module error is reported as Web not ready instead of a blank GUI.

Foreground API and frontend commands are still available when you need to run each service manually:

```powershell
cd quant
.\.venv\Scripts\python.exe scripts\run_api_server.py run
```

```powershell
cd apps\web
npm run dev
```

The frontend npm scripts preload a small Windows Vite compatibility shim for local `spawn EPERM` cases seen during Vite path probing.

## Governance Rules

- Frontend code only calls API contracts.
- Long-running sync work is handled by worker tasks.
- Formal data writes must pass normalization, schema validation, ingest batch recording, and quality checks.
- Research, factor, backtest, strategy, and trading modules consume stable data services or silver/gold datasets, not third-party providers directly.
- AI features can summarize, explain, search, and generate research workflows, but their persisted inputs must be traceable to governed datasets, news records, quality reports, tasks, and ingest batches.
