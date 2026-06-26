# Free MCP Data Source Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only free/community MCP candidate catalog while enriching the existing Tushare provider metadata.

**Architecture:** Keep registered adapters and MCP candidates separate. Real adapters remain in `AdapterRegistry` and `data_sources`; free/community MCP tools are exposed through a read-only catalog API and frontend section, so they cannot be enabled, smoke-tested, or used by automatic sync until a real adapter exists.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy-backed existing adapter registry, React, Ant Design, TanStack Query.

---

### Task 1: Backend Catalog API

**Files:**
- Modify: `apps/api/schemas/data_sources.py`
- Modify: `apps/api/services/data_source_service.py`
- Modify: `apps/api/routers/data_sources.py`
- Test: `tests/api/test_data_sources.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `GET /api/data-sources/catalog`, assert only free/community MCP candidates are listed, assert paid vendors are absent, and assert Tushare registered metadata mentions official MCP / sector capabilities.

- [ ] **Step 2: Run targeted tests**

Run: `pytest tests/api/test_data_sources.py -q`

Expected: new tests fail because the endpoint/schema do not exist yet.

- [ ] **Step 3: Implement minimal catalog**

Add a Pydantic read model and a static in-service list. Do not create a database table. Do not add candidates to `AdapterRegistry`.

- [ ] **Step 4: Run targeted tests again**

Run: `pytest tests/api/test_data_sources.py -q`

Expected: pass.

### Task 2: Frontend Candidate Directory

**Files:**
- Modify: `apps/web/src/features/data-sources/types.ts`
- Modify: `apps/web/src/features/data-sources/api.ts`
- Modify: `apps/web/src/pages/data-system/data-sources/DataSourcesPage.tsx`

- [ ] **Step 1: Add types/query hook**

Add a `DataSourceCatalogItem` type and `useDataSourceCatalogQuery()` hook.

- [ ] **Step 2: Render read-only catalog**

Show a compact free MCP candidate catalog below the registered source table. Actions are links only; no enable, health check, smoke test, or sync actions for candidates.

- [ ] **Step 3: Type-check**

Run: `cd apps/web; npm run type-check`

Expected: pass.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/data/data-source-and-sync-governance.md`
- Verify: API tests, frontend type-check/build, local browser screenshot.

- [ ] **Step 1: Document the boundary**

Update governance docs to state MCP is an adapter layer and candidate providers require authorization before real adapter work.

- [ ] **Step 2: Verify**

Run targeted API tests, frontend type-check/build, start dev services if needed, capture a screenshot of `/data-system/data-sources`.

- [ ] **Step 3: Delivery**

Summarize changed files and skipped work. Do not commit or push.
