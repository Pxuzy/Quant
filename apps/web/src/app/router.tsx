import { lazy } from 'react';
import {
  Navigate,
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  parseSearchWith,
  stringifySearchWith,
} from '@tanstack/react-router';
import { AppLayout } from '../layouts/AppLayout';

const DataSystemOverviewPage = lazy(() =>
  import('../pages/data-system/overview/DataSystemOverviewPage').then((module) => ({
    default: module.DataSystemOverviewPage,
  })),
);
const NewsPage = lazy(() =>
  import('../pages/news/NewsPage').then((m) => ({ default: m.NewsPage })),
);

const DashboardPage = lazy(() =>
  import('../pages/dashboard/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const PipelinePage = lazy(() =>
  import('../pages/data-system/pipeline/PipelinePage').then((module) => ({
    default: module.PipelinePage,
  })),
);
const AlertsPage = lazy(() =>
  import('../pages/data-system/alerts/AlertsPage').then((module) => ({
    default: module.AlertsPage,
  })),
);
const StocksWorkbenchPage = lazy(() =>
  import('../pages/data-system/stocks/StocksWorkbenchPage').then((module) => ({
    default: module.StocksWorkbenchPage,
  })),
);
const StockDetailPage = lazy(() =>
  import('../pages/data-system/stocks/StockDetailPage').then((module) => ({
    default: module.StockDetailPage,
  })),
);
const DataSourcesWorkbenchPage = lazy(() =>
  import('../pages/data-system/data-sources/DataSourcesPage').then((module) => ({
    default: module.DataSourcesPage,
  })),
);
const NumericSummaryPage = lazy(() =>
  import('../pages/data-system/numeric-summary/NumericSummaryPage').then((module) => ({
    default: module.NumericSummaryPage,
  })),
);
const DatabaseManagementPage = lazy(() =>
  import('../pages/data-system/database/DatabaseManagementPage').then((module) => ({
    default: module.DatabaseManagementPage,
  })),
);
const SyncTasksPage = lazy(() =>
  import('../pages/data-system/sync-tasks/SyncTasksPage').then((module) => ({
    default: module.SyncTasksPage,
  })),
);
export type StocksSearch = {
  keyword?: string;
  exchange?: string;
  industry?: string;
  market?: string;
  status?: string;
  dailyCoverage?: string;
  syncSource?: string;
  page?: number;
  pageSize?: number;
};

export type StockDetailSearch = {
  market?: string;
};

export type SyncTasksSearch = {
  status?: string;
  source?: string;
  taskType?: string;
  focus?: string;
  symbol?: string;
  market?: string;
  startDate?: string;
  endDate?: string;
  syncSource?: string;
  maxSymbols?: number;
  page?: number;
  pageSize?: number;
  taskId?: number;
};

export type DatabaseSearch = {
  market?: string;
  view?: string;
  lineageBatchId?: number;
  lineageDatasetName?: string;
  lineageSymbol?: string;
  lineageTradeDate?: string;
  lineageSource?: string;
  lineageStatus?: string;
  lineagePage?: number;
  lineagePageSize?: number;
  qualityDatasetName?: string;
  qualityStatus?: string;
  qualitySeverity?: string;
  qualityCheckedAt?: string;
  qualityPage?: number;
  qualityPageSize?: number;
};

export type DataQualitySearch = {
  datasetName?: string;
  status?: string;
  severity?: string;
  page?: number;
  pageSize?: number;
};

function stringSearch(value: unknown) {
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return undefined;
}

function numberSearch(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function parseSearchValue(value: string) {
  if (value === 'true') {
    return true;
  }
  if (value === 'false') {
    return false;
  }
  if (value !== '' && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return value;
}

function stringifySearchValue(value: unknown) {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

const rootRoute = createRootRoute({
  component: AppLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <Navigate to="/dashboard" replace />,
});

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboard',
  component: DashboardPage,
});

const overviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system',
  component: DataSystemOverviewPage,
});

const pipelineRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/pipeline',
  component: PipelinePage,
});

const alertsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/alerts',
  component: AlertsPage,
});

const stocksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/stocks',
  validateSearch: (search): StocksSearch => ({
    keyword: stringSearch(search.keyword),
    exchange: stringSearch(search.exchange),
    industry: stringSearch(search.industry),
    market: stringSearch(search.market),
    status: stringSearch(search.status),
    dailyCoverage: stringSearch(search.dailyCoverage),
    syncSource: stringSearch(search.syncSource),
    page: numberSearch(search.page),
    pageSize: numberSearch(search.pageSize),
  }),
  component: StocksWorkbenchPage,
});

const stockDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/stocks/$symbol',
  validateSearch: (search): StockDetailSearch => ({
    market: stringSearch(search.market),
  }),
  component: StockDetailPage,
});

const dataSourcesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/data-sources',
  component: DataSourcesWorkbenchPage,
});

;

const numericSummaryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/numeric-summary',
  component: NumericSummaryPage,
});

const databaseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/database',
  validateSearch: (search): DatabaseSearch => ({
    market: stringSearch(search.market),
    view: stringSearch(search.view),
    lineageBatchId: numberSearch(search.lineageBatchId),
    lineageDatasetName: stringSearch(search.lineageDatasetName),
    lineageSymbol: stringSearch(search.lineageSymbol),
    lineageTradeDate: stringSearch(search.lineageTradeDate),
    lineageSource: stringSearch(search.lineageSource),
    lineageStatus: stringSearch(search.lineageStatus),
    lineagePage: numberSearch(search.lineagePage),
    lineagePageSize: numberSearch(search.lineagePageSize),
    qualityDatasetName: stringSearch(search.qualityDatasetName),
    qualityStatus: stringSearch(search.qualityStatus),
    qualitySeverity: stringSearch(search.qualitySeverity),
    qualityCheckedAt: stringSearch(search.qualityCheckedAt),
    qualityPage: numberSearch(search.qualityPage),
    qualityPageSize: numberSearch(search.qualityPageSize),
  }),
  component: DatabaseManagementPage,
});

// Legacy redirects keep backward compatibility.

const syncTasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data-system/sync-tasks',
  validateSearch: (search): SyncTasksSearch => ({
    status: stringSearch(search.status),
    source: stringSearch(search.source),
    taskType: stringSearch(search.taskType),
    focus: stringSearch(search.focus),
    symbol: stringSearch(search.symbol),
    market: stringSearch(search.market),
    startDate: stringSearch(search.startDate),
    endDate: stringSearch(search.endDate),
    syncSource: stringSearch(search.syncSource),
    maxSymbols: numberSearch(search.maxSymbols),
    page: numberSearch(search.page),
    pageSize: numberSearch(search.pageSize),
    taskId: numberSearch(search.taskId),
  }),
  component: SyncTasksPage,
});

;

const newsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/news',
  component: NewsPage,
});

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/$',
  component: () => (
    <div style={{ padding: 48, textAlign: 'center' }}>
      <h2>404 - Not found</h2>
      <p style={{ color: '#999' }}>Check the route path.</p>
    </div>
  ),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  dashboardRoute,
  newsRoute,
  notFoundRoute,
  overviewRoute,
  pipelineRoute,
  alertsRoute,
  stocksRoute,
  stockDetailRoute,
  dataSourcesRoute,
  numericSummaryRoute,
  databaseRoute,
  syncTasksRoute,
]);

export const router = createRouter({
  routeTree,
  parseSearch: parseSearchWith(parseSearchValue),
  stringifySearch: stringifySearchWith(stringifySearchValue),
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
