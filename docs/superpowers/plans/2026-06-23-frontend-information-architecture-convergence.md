# Frontend Information Architecture Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收尾 Quant 前端信息架构，把数据系统收敛成清楚的股票研究台入口和数据可信后台入口。

**Architecture:** 保持现有 React + TanStack Router + Ant Design 页面边界，不新增依赖，不重写数据层。先把壳层导航和路由契约定稳，再把总控台、数值数据、数据源管理三个首要页面压成“当前结论、最短动作、必要诊断”，最后同步文档和做浏览器截图验收。

**Tech Stack:** React 18, Vite, TypeScript, Ant Design, TanStack Router, TanStack Query, GSAP, plain CSS.

---

## Scope

### In Scope

- 固定主导航的七个入口：总控台、新闻汇总、数值数据、股票池、数据源管理、同步调度、数据库管理。
- 让 `/data-system` 成为总控台主入口，继续兼容 `/data-system/overview` 跳转。
- 收敛总控台首屏，只保留结论、异常、关键状态、最短动作和数据流向入口。
- 收敛数值数据页，只回答新鲜度、覆盖缺口、质量和最近批次。
- 收敛数据源管理页，只回答 provider 是否可用、取样是否可信、下一步做什么。
- 更新功能矩阵和路线图状态。
- 运行 `npm run type-check`、`npm run build`，并用浏览器截图验收三个页面。

### Out of Scope

- 不新增后端 API。
- 不新增前端依赖或测试框架。
- 不改 worker、provider adapter、数据库 schema。
- 不做新闻闭环、自选股持久化、股票详情增强。
- 不 commit / push，除非用户明确说“提交”。

## Current Files

- Modify: `apps/web/src/layouts/AppLayout.tsx` - shell navigation and selected route state.
- Modify: `apps/web/src/app/router.tsx` - lazy route imports, redirects, search contracts.
- Modify: `apps/web/src/pages/data-system/overview/DataSystemOverviewPage.tsx` - total control page data derivation and layout.
- Modify: `apps/web/src/pages/data-system/overview/QuickActions.tsx` - compact primary actions.
- Modify: `apps/web/src/pages/data-system/overview/StatusSummaryCard.tsx` - current conclusion card.
- Modify: `apps/web/src/pages/data-system/overview/PipelineFlowCard.tsx` - source-to-quality flow actions.
- Modify: `apps/web/src/pages/data-system/numeric-summary/NumericSummaryPage.tsx` - numeric data overview.
- Modify: `apps/web/src/pages/data-system/data-sources/DataSourcesPage.tsx` - provider health and smoke sample page.
- Modify: `apps/web/src/styles.css` - shared density and responsive polish.
- Modify: `docs/product/feature-catalog.md` - visible entry and page responsibility status.
- Modify: `docs/status/roadmap.md` - mark this convergence step as completed after verification.

## Validation Commands

Run from `E:\hermes\workspace\Quant\apps\web`:

```powershell
npm run type-check
npm run build
```

Run from `E:\hermes\workspace\Quant` when full local smoke is useful:

```powershell
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd smoke
```

Browser verification target:

```text
http://127.0.0.1:5175/data-system
http://127.0.0.1:5175/data-system/numeric-summary
http://127.0.0.1:5175/data-system/data-sources
```

If port `5175` is not running, start with:

```powershell
.\scripts\quant-dev.cmd start-bg
```

---

### Task 1: Baseline and Failing Acceptance Check

**Files:**
- Read: `apps/web/src/layouts/AppLayout.tsx`
- Read: `apps/web/src/app/router.tsx`
- Read: `apps/web/src/pages/data-system/overview/DataSystemOverviewPage.tsx`
- Read: `apps/web/src/pages/data-system/numeric-summary/NumericSummaryPage.tsx`
- Read: `apps/web/src/pages/data-system/data-sources/DataSourcesPage.tsx`

- [ ] **Step 1: Capture current git state**

Run:

```powershell
git status --short
```

Expected: repository may already be dirty. Record unrelated files and do not revert them.

- [ ] **Step 2: Run the current frontend checks before edits**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run type-check
npm run build
```

Expected: either PASS, or FAIL with existing TypeScript/build errors. If this fails before edits, record the exact error and only continue if the failure is unrelated to the planned files.

- [ ] **Step 3: Capture current visual baseline**

Run:

```powershell
cd E:\hermes\workspace\Quant
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd start-bg
.\scripts\quant-dev.cmd smoke
```

Expected: API and Web are reported ready. If the lifecycle script reports Web not ready, use its log path before editing.

- [ ] **Step 4: Browser-check the failing acceptance criteria**

Open:

```text
http://127.0.0.1:5175/data-system
http://127.0.0.1:5175/data-system/numeric-summary
http://127.0.0.1:5175/data-system/data-sources
```

Expected current problems to look for:

- Main navigation does not expose exactly the seven target entries.
- Page labels still mix legacy dashboard/database wording.
- Overview, numeric summary, or data sources pages repeat the same source/quality/storage signals.
- The user cannot quickly tell the next action from the first viewport.

Save screenshots under a temporary path outside the repo, for example:

```text
C:\tmp\quant-baseline-overview.png
C:\tmp\quant-baseline-numeric-summary.png
C:\tmp\quant-baseline-data-sources.png
```

---

### Task 2: Stabilize Shell Navigation and Route Ownership

**Files:**
- Modify: `apps/web/src/layouts/AppLayout.tsx`
- Modify: `apps/web/src/app/router.tsx`

- [ ] **Step 1: Export the seven visible shell entries from `AppLayout.tsx`**

Replace the current `NAV_ITEMS` with a seven-entry model:

```tsx
const NAV_ITEMS: NavItem[] = [
  { key: 'overview', label: '总控台', path: '/data-system', icon: <Icons.DashboardOutlined />, group: 'workbench' },
  { key: 'news-summary', label: '新闻汇总', path: '/data-system/news-summary', icon: <Icons.ReadOutlined />, group: 'workbench' },
  { key: 'numeric-summary', label: '数值数据', path: '/data-system/numeric-summary', icon: <Icons.BarChartOutlined />, group: 'workbench' },
  { key: 'stocks', label: '股票池', path: '/data-system/stocks', icon: <Icons.TableOutlined />, group: 'workbench' },
  { key: 'data-sources', label: '数据源管理', path: '/data-system/data-sources', icon: <Icons.ApiOutlined />, group: 'admin' },
  { key: 'sync-tasks', label: '同步调度', path: '/data-system/sync-tasks', icon: <Icons.CloudSyncOutlined />, group: 'admin' },
  {
    key: 'database',
    label: '数据库管理',
    path: '/data-system/database',
    icon: <Icons.AreaChartOutlined />,
    aliases: ['/data-system/data-quality', '/data-system/datasets', '/data-system/trading-calendars'],
    group: 'admin',
  },
];
```

- [ ] **Step 2: Keep menu selection deterministic**

Keep `findNavItem` loop-based, but make `/data-system` exact before prefix routes:

```tsx
function findNavItem(pathname: string) {
  const exact = NAV_ITEMS.find((i) => pathname === i.path);
  if (exact) return exact;

  return (
    NAV_ITEMS.find((i) => pathname.startsWith(i.path + '/') || i.aliases?.some((a) => pathname.startsWith(a))) ??
    NAV_ITEMS[0]
  );
}
```

Expected: `/data-system/stocks/600519` selects `股票池`; `/data-system/database?view=quality` selects `数据库管理`; `/data-system` selects `总控台`.

- [ ] **Step 3: Update brand subtitle and header wording**

Use product wording:

```tsx
<Typography.Text className="brand-subtitle">个人股票研究工作台</Typography.Text>
```

Keep the header market chip as `A_SHARE`, and keep the top-right `补日线` action because it is a real data repair shortcut.

- [ ] **Step 4: Remove legacy top-level dashboard/news/data-source entry dependence**

In `router.tsx`, keep legacy routes for compatibility, but redirect daily entry points into the new IA:

```tsx
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <Navigate to="/data-system" replace />,
});
```

Leave `/dashboard`, `/news`, and `/data-sources` routes intact unless removing them would break existing links. They should not appear in the primary menu.

- [ ] **Step 5: Verify route contract**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run type-check
```

Expected: PASS. If route typing fails, fix the `navigate({ to })` target paths rather than weakening types.

---

### Task 3: Compress Overview to Decision, Actions, and Flow

**Files:**
- Modify: `apps/web/src/pages/data-system/overview/DataSystemOverviewPage.tsx`
- Modify: `apps/web/src/pages/data-system/overview/QuickActions.tsx`
- Modify: `apps/web/src/pages/data-system/overview/StatusSummaryCard.tsx`
- Modify: `apps/web/src/pages/data-system/overview/PipelineFlowCard.tsx`

- [ ] **Step 1: Add one boundary comment above derived state**

Add the comment directly before `const latestDailyWatermark = useMemo(...)`:

```tsx
// 总控台只做两件事：给出当前结论，并把用户导向最该先做的动作。
// 下面的派生状态只把后端快照压成首屏可读信息，不在 JSX 里临时拼逻辑。
```

Expected: comment describes ownership, not line-by-line behavior.

- [ ] **Step 2: Remove unused derived values**

If `latestDailyWatermark` remains unused after layout edits, delete:

```tsx
const latestDailyWatermark = useMemo(
  () => getLatestDailyWatermark(integrationOverview?.sync_watermarks ?? []),
  [integrationOverview?.sync_watermarks],
);
```

Then delete `getLatestDailyWatermark` if no longer referenced.

Expected: no unused TypeScript symbols.

- [ ] **Step 3: Make the overview heading product-oriented**

Use:

```tsx
<Typography.Title level={3}>总控台</Typography.Title>
<Typography.Text type="secondary">先判断今天能不能继续研究，再处理数据缺口和来源问题。</Typography.Text>
```

- [ ] **Step 4: Reduce quick actions to four stable commands**

In `QuickActions.tsx`, keep:

```tsx
<Tooltip title="刷新总控台数据">
  <Button icon={<ReloadOutlined />} onClick={onRefresh} />
</Tooltip>
<Button type="primary" icon={<CloudSyncOutlined />} loading={syncLoading} onClick={onSyncStocks}>
  更新股票池
</Button>
<Button icon={<BarChartOutlined />} onClick={onOpenNumericSummary}>
  看数值
</Button>
<Button onClick={onOpenStocks}>
  看股票池
</Button>
```

Expected: no extra explanatory text or hidden new feature.

- [ ] **Step 5: Keep `StatusSummaryCard` as the single decision card**

Keep `AlertBanner` at the top of `StatusSummaryCard`, one decision title, one decision description, and two actions:

```tsx
<Button type="primary" icon={<ArrowRightOutlined />} onClick={onDecisionAction}>
  {decisionActionLabel}
</Button>
<Button loading={dailySyncLoading} onClick={onDailySync}>
  {dailySyncLabel}
</Button>
```

Expected: no nested cards inside this card.

- [ ] **Step 6: Make `PipelineFlowCard` action targets match product ownership**

Use this click mapping:

```tsx
const handleClick = (key: string) => {
  switch (key) {
    case 'sources':
      onOpenSources();
      break;
    case 'sync':
      onOpenNumericSummary();
      break;
    case 'lake':
      onOpenDatabase();
      break;
    case 'quality':
      onOpenDatabase();
      break;
    case 'stocks':
      onOpenStocks();
      break;
  }
};
```

Expected: quality and lake go to database management; source goes to data source management; sync/numeric condition goes to numeric summary or sync tasks through the existing CTA.

- [ ] **Step 7: Verify overview compiles**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run type-check
```

Expected: PASS with no unused imports from deleted helpers.

---

### Task 4: Make Numeric Summary a Numeric Decision Page

**Files:**
- Modify: `apps/web/src/pages/data-system/numeric-summary/NumericSummaryPage.tsx`

- [ ] **Step 1: Add a module boundary comment**

Add near the top of the file, after constants/imports:

```tsx
// 数值数据页只回答三个问题：数据新鲜到哪天、覆盖缺口在哪里、最近批次是否稳定。
```

- [ ] **Step 2: Keep the existing helper functions**

Keep these helpers because they encode page-level decisions:

```tsx
coveragePercent(coverage)
qualityPassRate(total, passed)
daysSince(value)
formatDataAge(days)
hasDailyCoverageGap(coverage)
getBatchFinishedAt(batch)
getBatchRange(batch)
```

Expected: do not introduce a separate utility file unless multiple pages consume the same helpers after the edit.

- [ ] **Step 3: First viewport should show four numeric facts**

Ensure the top visible section shows:

- `最新日线日期`
- `日线完整度`
- `质量通过率`
- `最近批次`

Use existing API data from:

```tsx
const databaseStatusQuery = useDatabaseStatusQuery();
const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market });
const qualityOverviewQuery = useDataQualityOverviewQuery();
```

Expected: no new API calls.

- [ ] **Step 4: Keep one primary repair CTA**

When `hasDailyCoverageGap(coverageSummary)` is true, route to:

```tsx
void navigate({
  to: '/data-system/sync-tasks',
  search: {
    focus: 'daily-bars-market-repair',
    market,
  },
});
```

When no coverage gap exists, route the secondary drilldown to:

```tsx
void navigate({ to: '/data-system/database', search: { market, view: 'lineage' } });
```

Expected: the page does not duplicate the full database management page.

- [ ] **Step 5: Reduce below-fold content**

Keep at most:

- One coverage/quality summary block.
- One recent ingest batch table.
- One empty/error state using existing Ant Design components.

Remove or collapse storage details that are already present in database management.

- [ ] **Step 6: Verify numeric summary compiles**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run type-check
```

Expected: PASS. If JSX grows hard to scan, extract only local render helpers inside the same file; do not create a new abstraction for one use.

---

### Task 5: Densify Data Source Management

**Files:**
- Modify: `apps/web/src/pages/data-system/data-sources/DataSourcesPage.tsx`

- [ ] **Step 1: Keep V1 provider boundary**

Keep:

```tsx
const V1_DATA_SOURCE_CODES = new Set(['akshare', 'baostock', 'adata', 'tushare', 'stock_sdk']);
```

Expected: only these five providers are shown in this phase.

- [ ] **Step 2: Add a module boundary comment**

Add near `V1_DATA_SOURCE_CODES`:

```tsx
// 数据源管理只负责三件事：判断能不能用、快速看样本、把用户送到下一步。
// 不在这里展开上游工具、插件市场或完整文档墙。
```

- [ ] **Step 3: Keep compact status functions**

Keep and reuse:

```tsx
explainSourceStatus(source)
explainSourceAction(source)
tokenStatusTag(source)
formatDailyBarExchangeCoverage(source)
renderSmokeHistory(source)
renderSmokeSample(source)
```

Expected: no new provider abstraction, no new global state.

- [ ] **Step 4: Order smoke sample fields for scanability**

Keep `preferredSampleFields` in this order:

```tsx
const preferredSampleFields = [
  'symbol',
  'name',
  'exchange',
  'market',
  'trade_date',
  'pre_close',
  'open',
  'high',
  'low',
  'close',
  'volume',
  'amount',
  'source',
];
```

- [ ] **Step 5: Make each provider card answer four questions**

Each rendered source card should show, in the first visible block:

- enabled / disabled
- health status
- auth token status
- supported capabilities

The action row should keep:

- health check
- smoke test
- enable / disable
- priority update
- sync stock pool when relevant

Expected: no long provider encyclopedia text.

- [ ] **Step 6: Verify data sources compiles**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run type-check
```

Expected: PASS with no new dependency.

---

### Task 6: Shared Visual Density and Responsive Polish

**Files:**
- Modify: `apps/web/src/styles.css`

- [ ] **Step 1: Keep page sections unframed, cards only for real panels**

Use existing classes:

```css
.workbench
.workbench-heading
.overview-page
.overview-panel
.overview-status-strip
.numeric-summary-page
.data-sources-page
```

Expected: do not add decorative hero sections, gradient blobs, or nested cards.

- [ ] **Step 2: Tighten first viewport density**

Use a compact baseline:

```css
.overview-status-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
```

For mobile:

```css
@media (max-width: 900px) {
  .overview-status-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .overview-status-strip {
    grid-template-columns: 1fr;
  }
}
```

Expected: no horizontal overflow at desktop or mobile widths.

- [ ] **Step 3: Keep text inside controls**

If any button label wraps badly, prefer shorter labels:

```text
看数值
看股票池
检查来源
补日线
```

Expected: no viewport-scaled font sizes and no negative letter spacing.

- [ ] **Step 4: Verify build after CSS**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run build
```

Expected: PASS.

---

### Task 7: Documentation Sync

**Files:**
- Modify: `docs/product/feature-catalog.md`
- Modify: `docs/status/roadmap.md`

- [ ] **Step 1: Update feature catalog page ownership**

In `docs/product/feature-catalog.md`, ensure these responsibilities are present:

```markdown
| 总控台 | 工作台层 | 判断今天能否继续研究，显示数据新鲜度、来源健康、质量风险和最短动作 |
| 新闻汇总 | 工作台层 | 新闻入口，后续承接新闻闭环和股票关联 |
| 数值数据 | 工作台层 | 显示日线新鲜度、覆盖缺口、质量通过率和最近批次 |
| 股票池 | 工作台层 | 股票浏览、搜索、筛选和单股详情入口 |
| 数据源管理 | 控制面 | provider 启停、优先级、健康检查和真实取样 |
| 同步调度 | 控制面 | 股票池、单股日线、交易日历和市场级补齐任务 |
| 数据库管理 | 控制面 | 数据集、新鲜度、缺口、批次血缘和质量风险 |
```

Expected: wording matches product definition and implementation.

- [ ] **Step 2: Update roadmap status**

In `docs/status/roadmap.md`, update the current status summary after implementation:

```markdown
- 前端主导航已收敛为总控台、新闻汇总、数值数据、股票池、数据源管理、同步调度和数据库管理七个入口。
- 总控台、数值数据和数据源管理已按“结论 + 最短动作 + 必要诊断”减噪。
```

Move or annotate the P1 item `前端信息架构` as completed for this slice, while leaving news/self-selected stocks as future work.

- [ ] **Step 3: Verify docs do not claim unbuilt features**

Search:

```powershell
cd E:\hermes\workspace\Quant
rg -n "已完成|自选股|新闻闭环|回测|实盘|插件" docs\product\feature-catalog.md docs\status\roadmap.md
```

Expected: docs do not say news closed-loop, self-selected stocks, backtest, live trading, or plugin marketplace are implemented.

---

### Task 8: Full Verification and Visual Evidence

**Files:**
- None

- [ ] **Step 1: Run final static checks**

Run:

```powershell
cd E:\hermes\workspace\Quant\apps\web
npm run type-check
npm run build
```

Expected: both PASS.

- [ ] **Step 2: Run lifecycle smoke**

Run:

```powershell
cd E:\hermes\workspace\Quant
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd smoke
```

Expected: API health is OK, Web HTML is OK, and `/src/main.tsx` is OK.

- [ ] **Step 3: Browser-check desktop routes**

Open:

```text
http://127.0.0.1:5175/data-system
http://127.0.0.1:5175/data-system/numeric-summary
http://127.0.0.1:5175/data-system/data-sources
```

Expected:

- Shell shows exactly seven primary entries.
- Overview first viewport shows current conclusion, key facts, and action path.
- Numeric summary shows freshness, coverage, quality, and latest batch.
- Data sources shows five V1 providers with compact health/smoke/action state.
- No console errors from route rendering.

- [ ] **Step 4: Browser-check mobile width**

Use a mobile viewport around `390 x 844`.

Expected:

- No horizontal overflow.
- Buttons keep readable labels.
- Status tiles wrap without overlapping.
- Provider cards remain scanable.

- [ ] **Step 5: Save visual evidence**

Save screenshots under `C:\tmp`:

```text
C:\tmp\quant-final-overview-desktop.png
C:\tmp\quant-final-numeric-summary-desktop.png
C:\tmp\quant-final-data-sources-desktop.png
C:\tmp\quant-final-overview-mobile.png
```

Expected: screenshots are available for the final report.

- [ ] **Step 6: Show final diff summary**

Run:

```powershell
cd E:\hermes\workspace\Quant
git diff --stat
git diff -- apps/web/src/layouts/AppLayout.tsx apps/web/src/app/router.tsx apps/web/src/pages/data-system/overview apps/web/src/pages/data-system/numeric-summary apps/web/src/pages/data-system/data-sources apps/web/src/styles.css docs/product/feature-catalog.md docs/status/roadmap.md
```

Expected: diff is limited to the planned files. Do not stage, commit, or push.

---

## Self-Review

### Spec Coverage

- Seven-entry navigation: Task 2.
- Overview conclusion and action compression: Task 3.
- Numeric summary focus: Task 4.
- Data source page density: Task 5.
- CSS and responsive proof: Task 6 and Task 8.
- Docs sync: Task 7.
- Quant workflow verification and screenshots: Task 8.

### Placeholder Scan

No placeholder markers or unspecified implementation steps remain. Each task has concrete files, commands, and expected results.

### Type Consistency

Route names and paths are consistent across tasks:

- `overview` -> `/data-system`
- `news-summary` -> `/data-system/news-summary`
- `numeric-summary` -> `/data-system/numeric-summary`
- `stocks` -> `/data-system/stocks`
- `data-sources` -> `/data-system/data-sources`
- `sync-tasks` -> `/data-system/sync-tasks`
- `database` -> `/data-system/database`

### Ponytail Notes

- skipped: new test framework, add when frontend behavior needs repeatable unit-level regression coverage beyond `type-check`, `build`, and browser screenshots.
- skipped: API changes, add when pages need data not already available through existing contracts.
- skipped: shared helper extraction, add when at least two pages need the same non-trivial helper after this convergence.
- skipped: commit/push steps, add only after the user explicitly says `提交`.
