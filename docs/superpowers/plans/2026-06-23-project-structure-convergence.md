# Project Structure Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Quant repository feel structurally deliberate without forcing it into an unrelated single-`app/` template.

**Architecture:** Keep the existing monorepo shape: `apps/api` owns FastAPI business code, `apps/web` owns React, `apps/worker` owns task execution entrypoints, `scripts` owns local developer lifecycle commands, and `quant` remains a compatibility/runtime-material area. First move only the legacy market workbench service into the API service layer, while keeping old imports working.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React/Vite, PowerShell lifecycle scripts.

---

### Task 1: Move legacy market service under API services

**Files:**
- Create: `apps/api/services/market_service.py`
- Modify: `quant/services/market_service.py`
- Modify: `quant/services/__init__.py`
- Modify: `apps/api/routers/market.py`
- Test: `tests/api/test_market_service_structure.py`

- [ ] **Step 1: Write the failing structure test**

Create `tests/api/test_market_service_structure.py`:

```python
from apps.api.services import market_service as api_market_service
from quant.services import market_service as legacy_market_service


def test_market_service_legacy_path_reexports_api_service():
    exported_names = [
        "get_history_kline",
        "get_index_quotes",
        "get_news",
        "get_realtime_quotes",
        "get_sector_stocks",
        "search_stock",
    ]

    for name in exported_names:
        assert getattr(legacy_market_service, name) is getattr(api_market_service, name)
```

- [ ] **Step 2: Run the test and confirm it fails before migration**

Run:

```powershell
.\quant\.venv\Scripts\python.exe -m pytest tests/api/test_market_service_structure.py -q
```

Expected before implementation: import failure for `apps.api.services.market_service`.

- [ ] **Step 3: Copy the existing implementation into the API service layer**

Copy the current byte-for-byte implementation from `quant/services/market_service.py` to `apps/api/services/market_service.py`. Do not rewrite the provider logic in this task.

- [ ] **Step 4: Turn the old module into a compatibility re-export**

Replace `quant/services/market_service.py` with imports from `apps.api.services.market_service`, preserving the six public functions.

- [ ] **Step 5: Point the API router at the new service location**

Change `apps/api/routers/market.py` so it imports market functions from `apps.api.services.market_service`.

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
.\quant\.venv\Scripts\python.exe -m pytest tests/api/test_market_service_structure.py -q
.\quant\.venv\Scripts\python.exe -m py_compile apps/api/routers/market.py apps/api/services/market_service.py quant/services/market_service.py
```

Expected: all pass.

### Task 2: Document the intended repository boundaries

**Files:**
- Create: `docs/architecture/project-structure.md`
- Modify: `docs/architecture/system-overview.md`
- Modify: `docs/operations/development-runbook.md`

- [ ] **Step 1: Add `project-structure.md`**

Document the current target boundaries:

```text
apps/api     FastAPI routers, services, repositories, schemas, models, adapters
apps/web     React user interface
apps/worker  CLI/task execution entrypoints
scripts      local developer lifecycle scripts
quant        runtime materials and compatibility shims
tests        API and worker tests
docs         product, architecture, and operations documentation
```

- [ ] **Step 2: Link it from architecture overview**

Add a short pointer from `docs/architecture/system-overview.md` to `docs/architecture/project-structure.md`.

- [ ] **Step 3: Clarify runtime materials in runbook**

Clarify that `quant/scripts/run_api_server.py` is a launcher/runtime script, while business API code belongs under `apps/api`.

### Task 3: Verify no unrelated changes were lost

**Files:**
- Read-only: current git diff and test output

- [ ] **Step 1: Check working tree**

Run:

```powershell
git status --short
git diff --stat
```

Expected: existing user changes remain visible; no `git reset` or destructive cleanup.

- [ ] **Step 2: Run validation**

Run:

```powershell
.\quant\.venv\Scripts\python.exe -m pytest tests/api/test_market_service_structure.py -q
cd apps\web
npm run type-check
```

Expected: pass. Broader API/worker tests may be run after this first refactor if runtime state is stable.
