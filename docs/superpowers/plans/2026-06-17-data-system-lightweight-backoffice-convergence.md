# 数据系统浅色后台收敛 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把数据系统前端收敛成浅色、清楚、可扫读的管理后台，保留七个关键入口，让总控台、数值汇总、新闻汇总和数据源管理都能直接用，其他信息降级为辅助钻取页。

**Architecture:** 保持现有路由与页面文件顺序不重排，只收紧导航层级和页面信息密度。主壳层保留七个关键入口：总控台、新闻汇总、数值数据、股票池、数据源管理、同步调度、数据库管理；总控台负责“当前结论 + 最短动作”，数值汇总负责“数值链路判断”，数据源管理负责“健康 + 取样 + 可用性”。样式层只做浅色管理后台收敛，不引入新的视觉语言。

**Tech Stack:** React 18, Vite, TypeScript, Ant Design, TanStack Router, TanStack Query, GSAP, plain CSS.

---

### Task 1: 收紧主导航和路由角色

**Files:**
- Modify: `apps/web/src/layouts/AppLayout.tsx`
- Modify: `apps/web/src/app/router.tsx`

- [ ] **Step 1: Rewrite the menu model so the shell exposes the seven key entries the user actually needs every day.**

```tsx
const mainMenuItems = [
  { key: 'overview', icon: <DashboardOutlined />, label: '总控台' },
  { key: 'news-summary', icon: <ReadOutlined />, label: '新闻汇总' },
  { key: 'numeric-summary', icon: <BarChartOutlined />, label: '数值数据' },
  { key: 'stocks', icon: <TableOutlined />, label: '股票池' },
  { key: 'data-sources', icon: <ApiOutlined />, label: '数据源管理' },
  { key: 'sync-tasks', icon: <SyncOutlined />, label: '同步调度' },
  { key: 'database', icon: <AreaChartOutlined />, label: '数据库管理' },
] as const;
```

- [ ] **Step 2: Keep `/data-system/news-summary` and `/data-system/numeric-summary` as visible routes and visible menu entries, because they are part of the key daily workflow.**

- [ ] **Step 3: Update selected-key fallback so each visible route keeps its own menu state and deep routes fall back to their parent area.**

```tsx
if (pathname.startsWith('/data-system/news-summary')) {
  return 'news-summary';
}
if (pathname.startsWith('/data-system/numeric-summary')) {
  return 'numeric-summary';
}
```

- [ ] **Step 4: Run `npm run type-check` from `apps/web` and confirm the shell still compiles.**

---

### Task 2: Compress overview page to current conclusion + 6 actions + 3 tabs

**Files:**
- Modify: `apps/web/src/pages/data-system/overview/DataSystemOverviewPage.tsx`

- [ ] **Step 1: Add a short module comment block above the derived-state cluster that explains what the page owns.**

```tsx
// 总控台只做两件事：给出当前结论，并把用户导向最该先做的动作。
// 下面的派生状态只把后端快照压成首屏可读信息，不在 JSX 里临时拼逻辑。
```

- [ ] **Step 2: Keep the existing section order, but merge repeated explanation cards into one decision block plus one 6-tile action board.**

- [ ] **Step 3: Move the detailed status into three tabs: `数值链路`, `来源与任务`, `质量与存储`; each tab should show the smallest useful table or summary, not a second dashboard.**

```tsx
const diagnosticTabs = [
  { key: 'numbers', label: '数值链路', children: <NumericChainPanel /> },
  { key: 'sources', label: '来源与任务', children: <SourceTaskPanel /> },
  { key: 'storage', label: '质量与存储', children: <QualityStoragePanel /> },
];
```

- [ ] **Step 4: Remove redundant supporting blocks that restate the same signal, especially duplicated source and quality callouts below the fold.**

- [ ] **Step 5: Run `npm run build` from `apps/web` and verify the page still renders with the same four action tiles and the three diagnostic tabs.**

---

### Task 3: Make numeric-summary a true numeric overview

**Files:**
- Modify: `apps/web/src/pages/data-system/numeric-summary/NumericSummaryPage.tsx`

- [ ] **Step 1: Add section comments that separate summary metrics, coverage signals, and recent batch drill-downs.**

```tsx
// 数值汇总页只回答三个问题：数据新鲜到哪天、覆盖缺口在哪里、最近批次是否稳定。
```

- [ ] **Step 2: Reduce the page to a compact strip of KPIs, a coverage and quality summary row, and one recent-batch table.**

- [ ] **Step 3: Keep the repair CTA as the main action, and route it to sync tasks with `focus: 'daily-bars-market-repair'` when coverage is incomplete.**

- [ ] **Step 4: Remove any text that duplicates the database management page, and keep numeric-summary focused on decision support instead of storage detail.**

- [ ] **Step 5: Run `npm run type-check` and `npm run build` from `apps/web`; confirm the page still shows the latest data date, coverage rate, quality pass rate, and latest batch.**

---

### Task 4: Densify data-sources page

**Files:**
- Modify: `apps/web/src/pages/data-system/data-sources/DataSourcesPage.tsx`

- [ ] **Step 1: Add a module boundary comment so the page reads as `source health + smoke sample + one action row`, not a provider encyclopedia.**

```tsx
// 数据源管理只负责三件事：判断能不能用、快速看样本、把用户送到下一步。
// 不在这里展开上游工具、插件市场或完整文档墙。
```

- [ ] **Step 2: Keep the V1 provider filter, but make the first screen show enabled status, health status, auth state, capabilities, and last smoke result in one compact card.**

- [ ] **Step 3: Collapse the sample section into a single reusable smoke block with fields ordered by `symbol / name / exchange / market / trade_date / open / high / low / close / volume / amount / source`.**

- [ ] **Step 4: Keep health check, smoke test, enable/disable, and priority actions visible, but reduce explanation copy to one short line per source.**

- [ ] **Step 5: Run `npm run build` from `apps/web` and browser-check that the page still exposes the five V1 data-source providers only.**

---

### Task 5: Finish light-theme polish and module comments

**Files:**
- Modify: `apps/web/src/styles.css`

- [ ] **Step 1: Trim the most visually heavy background and shadow combinations so the UI stays airy and flat enough for scanning.**

- [ ] **Step 2: Keep the existing light palette, but tighten card radii, table borders, and section spacing on `overview`, `numeric-summary`, and `data-sources`.**

- [ ] **Step 3: Add or retain concise comments only at module boundaries and derived-state clusters; do not add line-by-line narration.**

```css
/* 总控台、数值汇总、数据源管理共享同一套浅色后台密度。 */
```

- [ ] **Step 4: Re-run `npm run type-check` from `apps/web` and confirm the CSS changes do not introduce layout regressions.**

---

### Task 6: Browser and build verification

**Files:**
- None

- [ ] **Step 1: Start the app on a local port if it is not already running.**

Run in `apps/web`: `npm run dev -- --host 127.0.0.1 --port 5174`

Expected: Vite serves the app at `http://127.0.0.1:5174`.

- [ ] **Step 2: Run the static checks.**

Run in `apps/web`: `npm run type-check`

Expected: no TypeScript errors.

Run in `apps/web`: `npm run build`

Expected: production build completes successfully.

- [ ] **Step 3: Open `http://127.0.0.1:5174/data-system/overview`, `http://127.0.0.1:5174/data-system/numeric-summary`, and `http://127.0.0.1:5174/data-system/data-sources`.**

Expected: no horizontal overflow, the main action is obvious on each page, and the shell presents the seven daily entries: 总控台、新闻汇总、数值数据、股票池、数据源管理、同步调度、数据库管理.

- [ ] **Step 4: Confirm the user-facing signals.**

Expected: overview shows the current conclusion and the key function map; numeric-summary shows freshness, coverage, quality, and recent batches instead of storage noise; data-sources shows V1 providers with health and smoke results; `news-summary` opens directly from the primary menu.

---

### Self-Review

1. Coverage: shell/nav, overview, numeric-summary, data-sources, styles, verification.
2. Placeholder scan: none.
3. Type consistency: keep route keys `overview`, `news-summary`, `numeric-summary`, `stocks`, `data-sources`, `sync-tasks`, `database` visible in the shell.

### Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-data-system-lightweight-backoffice-convergence.md`.

Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session with checkpoint reviews.

Which approach?
