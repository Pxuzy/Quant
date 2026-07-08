/**
 * Constants, types, and utility functions extracted from DatabaseManagementPage.
 * Pure logic — no JSX, no React hooks.
 */
import type { Dayjs } from 'dayjs';
import type { Dataset } from '../../../../features/datasets/types';
import type { DatasetSnapshot, DatabaseCoverageSummary, SyncWatermark } from '../../../../features/database/types';
import type { DataSource, DataSourceCapability, DataSourceProviderMetadata, DataSourceSmokeSummary } from '../../../../features/data-sources/types';
import type { DataQualityReport } from '../../../../features/data-quality/types';
import type { TradingCalendarDay } from '../../../../features/trading-calendars/types';
import {
  formatAuthMode,
  formatCapability,
  formatExchange,
  formatMarket,
  formatProviderType,
  formatStability,
  formatStorageType,
  aShareMarketOptions,
} from '../../../../shared/domain/labels';
import { formatDate, formatDateTime, formatNumber } from '../../../../shared/components/formatters';

export const FIRST_PAGE = 1;
export const DATASET_PAGE_SIZE = 8;
export const CALENDAR_PAGE_SIZE = 8;
export const REPORT_PAGE_SIZE = 8;
export const LINEAGE_PAGE_SIZE = 8;
export const DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20;
export const DEFAULT_MARKET = 'A_SHARE';
export const V1_DATA_SOURCE_CODES = new Set(['akshare', 'baostock', 'stock_sdk']);

export const databaseMarketOptions = aShareMarketOptions;

export const lineageDatasetOptions = [
  { label: '全部数据集', value: '' },
  { label: '日线行情', value: 'daily_bars' },
  { label: '股票池', value: 'stocks' },
  { label: '交易日历', value: 'trading_calendars' },
];

export const lineageStatusOptions = [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '运行中', value: 'running' },
];

export const qualityStatusOptions = [
  { label: '全部状态', value: '' },
  { label: '通过', value: 'good' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' },
];

export const qualitySeverityOptions = [
  { label: '全部级别', value: '' },
  { label: '信息', value: 'info' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' },
];


export type DatasetMetricSource = Pick<Dataset, 'latest_data_date' | 'row_count' | 'storage_type'>;
export type FreshnessDatasetName = 'stocks' | 'daily_bars' | 'trading_calendars';

export type FreshnessItem = {
  datasetName: FreshnessDatasetName;
  title: string;
  description: string;
  latestDate?: string | null;
  source?: string | null;
  rowCount: number;
  qualityStatus: string;
  storageType?: string | null;
  actionLabel: string;
  actionPath: '/data-system/stocks' | '/data-system/sync-tasks';
  actionSearch?: { focus?: string };
};

export type RepairSearch = {
  focus?: string;
  market?: string;
  symbol?: string;
  startDate?: string;
  endDate?: string;
  syncSource?: string;
  maxSymbols?: number;
};

export type QualityAction = {
  label: string;
  to: '/data-system/sync-tasks' | '/data-system/stocks' | '/data-system/database';
  search?: RepairSearch | { qualityDatasetName?: string; qualityPage?: number; qualityPageSize?: number };
};

export type CalendarCoverageStats = {
  coverageStart?: string | null;
  coverageEnd?: string | null;
  latestDate?: string | null;
  loadedStart?: string | null;
  loadedEnd?: string | null;
  loadedTotal: number;
  loadedOpenDays: number;
  loadedClosedDays: number;
};

export type LineageFilterValues = {
  batchId?: number;
  datasetName?: string;
  symbol?: string;
  tradeDate?: Dayjs;
  source?: string;
  status?: string;
};

export type TraceQualityReportBatch = (report: DataQualityReport) => void;


export function getLatestDatasetDate(datasets: DatasetMetricSource[]) {
  const dates = datasets
    .map((dataset) => dataset.latest_data_date)
    .filter((date): date is string => Boolean(date))
    .sort();
  return dates[dates.length - 1];
}

export function getDatasetStorageSummary(datasets: DatasetMetricSource[]) {
  return datasets.reduce<Record<string, number>>((summary, dataset) => {
    const storageType = dataset.storage_type || 'unknown';
    summary[storageType] = (summary[storageType] ?? 0) + 1;
    return summary;
  }, {});
}

export function getDatasetRowsTotal(datasets: DatasetMetricSource[]) {
  return datasets.reduce((sum, dataset) => sum + (dataset.row_count ?? 0), 0);
}

export function getDatasetSnapshotByName(snapshots: DatasetSnapshot[], datasetName: string) {
  return snapshots.find((snapshot) => snapshot.dataset_name === datasetName);
}

export function getSourceCapabilities(source: DataSource): DataSourceCapability {
  return source.capabilities ?? source.config_json?.capabilities ?? {};
}

export function getSourceMetadata(source: DataSource): DataSourceProviderMetadata {
  return source.provider_metadata ?? source.config_json?.provider_metadata ?? {};
}

export function getSourceLastSmoke(source: DataSource): DataSourceSmokeSummary | undefined {
  return source.config_json?.last_smoke_test;
}

export function formatSourceHealthMessage(source: DataSource) {
  if (source.config_json?.last_health_message && typeof source.config_json.last_health_message === 'string') {
    return source.config_json.last_health_message;
  }
  const lastSmoke = getSourceLastSmoke(source);
  if (lastSmoke?.message) {
    return lastSmoke.message;
  }
  if (source.health_status === 'healthy') {
    return '最近健康检查通过。';
  }
  if (source.health_status === 'unavailable') {
    return '依赖、凭证或上游暂不可用。';
  }
  if (source.health_status === 'unhealthy') {
    return '最近健康检查未通过。';
  }
  return '尚未完成健康检查。';
}

export function formatCapabilitySummary(capabilities: DataSourceCapability) {
  const items = [
    capabilities.stock_list ? formatCapability('stock_list') : null,
    capabilities.daily_bars ? formatCapability('daily_bars') : null,
    capabilities.calendars ? formatCapability('calendars') : null,
  ].filter(Boolean);

  return items.length ? items.join(' / ') : '未声明核心能力';
}

export function formatDailyBarExchanges(capabilities: DataSourceCapability) {
  if (!capabilities.daily_bars) {
    return '不提供日线';
  }
  const exchanges = capabilities.daily_bar_exchanges;
  if (!Array.isArray(exchanges) || exchanges.length === 0) {
    return '日线交易所未声明';
  }
  return exchanges.map((exchange) => formatExchange(exchange)).join(' / ');
}

export function formatSmokeSample(sample?: Array<Record<string, unknown>>) {
  if (!sample?.length) {
    return '暂无标准化样本';
  }
  const first = sample[0];
  const compactFields = ['symbol', 'name', 'trade_date', 'close', 'is_open', 'source']
    .map((field) => {
      const value = first[field];
      return value === undefined || value === null || value === '' ? null : `${field}: ${String(value)}`;
    })
    .filter(Boolean);
  return compactFields.length ? compactFields.join(' / ') : JSON.stringify(first);
}

export function getDateRange(dates: string[]) {
  const sortedDates = [...dates].sort();
  return {
    start: sortedDates[0],
    end: sortedDates[sortedDates.length - 1],
  };
}

export function getCalendarCoverageStats(
  calendars: TradingCalendarDay[],
  coverage?: DatabaseCoverageSummary,
  snapshot?: DatasetSnapshot,
): CalendarCoverageStats {
  const calendarDates = calendars.map((day) => day.trade_date).filter(Boolean);
  const loadedRange = getDateRange(calendarDates);
  return {
    coverageStart: coverage?.coverage_start_date,
    coverageEnd: coverage?.coverage_end_date,
    latestDate: coverage?.calendar_latest_date ?? snapshot?.latest_data_date ?? loadedRange.end,
    loadedStart: loadedRange.start,
    loadedEnd: loadedRange.end,
    loadedTotal: calendars.length,
    loadedOpenDays: calendars.filter((day) => day.is_open).length,
    loadedClosedDays: calendars.filter((day) => !day.is_open).length,
  };
}

export function getDatasetFreshnessItems(snapshots: DatasetSnapshot[]): FreshnessItem[] {
  const stocks = getDatasetSnapshotByName(snapshots, 'stocks');
  const dailyBars = getDatasetSnapshotByName(snapshots, 'daily_bars');
  const calendars = getDatasetSnapshotByName(snapshots, 'trading_calendars');

  return [
    {
      datasetName: 'stocks',
      title: '股票池',
      description: 'A 股基础股票列表',
      latestDate: stocks?.latest_data_date,
      source: stocks?.source,
      rowCount: stocks?.row_count ?? 0,
      qualityStatus: stocks?.quality_status ?? 'unknown',
      storageType: stocks?.storage_type,
      actionLabel: '查看股票池',
      actionPath: '/data-system/stocks',
    },
    {
      datasetName: 'daily_bars',
      title: '日线行情',
      description: 'OHLCV、成交额、复权口径',
      latestDate: dailyBars?.latest_data_date,
      source: dailyBars?.source,
      rowCount: dailyBars?.row_count ?? 0,
      qualityStatus: dailyBars?.quality_status ?? 'unknown',
      storageType: dailyBars?.storage_type,
      actionLabel: '补日线数据',
      actionPath: '/data-system/sync-tasks',
      actionSearch: { focus: 'daily-bars-market-repair' },
    },
    {
      datasetName: 'trading_calendars',
      title: '交易日历',
      description: '开市日、休市日、覆盖窗口',
      latestDate: calendars?.latest_data_date,
      source: calendars?.source,
      rowCount: calendars?.row_count ?? 0,
      qualityStatus: calendars?.quality_status ?? 'unknown',
      storageType: calendars?.storage_type,
      actionLabel: '同步日历',
      actionPath: '/data-system/sync-tasks',
      actionSearch: { focus: 'calendars' },
    },
  ];
}

export function getFreshnessTagColor(item: FreshnessItem) {
  if (!item.latestDate || item.rowCount <= 0) {
    return 'default';
  }
  if (item.qualityStatus === 'good') {
    return 'green';
  }
  if (item.qualityStatus === 'warning') {
    return 'warning';
  }
  return 'red';
}

export function getMetadataStoreLabel(kind?: string) {
  if (!kind || kind === '-') {
    return '-';
  }
  if (kind === 'SQLite') {
    return '本地元数据';
  }
  if (kind === 'PostgreSQL') {
    return '生产元数据';
  }
  return `${kind} 元数据库`;
}

export function formatRange(start?: string | null, end?: string | null) {
  if (!start && !end) {
    return '-';
  }
  if (start && end && start !== end) {
    return `${formatDate(start)} ~ ${formatDate(end)}`;
  }
  return formatDate(end || start);
}

export function formatWatermarkScope(watermark: SyncWatermark) {
  const market = formatMarket(watermark.market);
  return watermark.symbol ? `${market} / ${watermark.symbol}` : market;
}

export function formatRepairRange(watermark: SyncWatermark) {
  return formatRange(watermark.repair_start_date, watermark.repair_end_date);
}

export function getDailyCompletenessPercent(coverage?: DatabaseCoverageSummary) {
  if (coverage?.daily_completeness === undefined || coverage.daily_completeness === null) {
    return undefined;
  }
  return coverage.daily_completeness * 100;
}

export function isCoverageDegraded(coverage?: DatabaseCoverageSummary) {
  return coverage?.coverage_status === 'degraded';
}

export function findRepairableDailyWatermark(watermarks: SyncWatermark[]) {
  return watermarks.find((watermark) => watermark.dataset_name === 'daily_bars' && Boolean(watermark.repair_reason));
}

export function isMarketDailyRepairHint(watermark: SyncWatermark) {
  return watermark.dataset_name === 'daily_bars' && watermark.repair_reason?.includes('该市场同区间日线');
}

export function getMarketRepairSearch(coverage?: DatabaseCoverageSummary, watermark?: SyncWatermark): RepairSearch {
  return {
    focus: 'daily-bars-market-repair',
    market: watermark?.market ?? coverage?.market,
    startDate: watermark?.repair_start_date ?? coverage?.coverage_start_date ?? undefined,
    endDate: watermark?.repair_end_date ?? coverage?.coverage_end_date ?? undefined,
    syncSource: watermark?.requested_source || watermark?.source || undefined,
    maxSymbols: DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
  };
}

export function getQualityReportAction(report: DataQualityReport, coverage?: DatabaseCoverageSummary): QualityAction | undefined {
  if (report.severity === 'info' || report.status === 'good') {
    return undefined;
  }

  if (report.dataset_name === 'daily_bars') {
    if (
      report.check_type === 'missing_trade_date' ||
      report.check_type === 'missing_trade_date_by_symbol' ||
      report.check_type === 'stock_pool_missing_daily_bars'
    ) {
      return {
        label: '补齐日线',
        to: '/data-system/sync-tasks',
        search: getMarketRepairSearch(coverage),
      };
    }

    return {
      label: '看批次',
      to: '/data-system/sync-tasks',
      search: { focus: 'daily-bars' },
    };
  }

  if (report.dataset_name === 'stocks' || report.dataset_name === 'stock_list') {
    return {
      label: '同步股票池',
      to: '/data-system/sync-tasks',
      search: { focus: 'stock-list' },
    };
  }

  if (report.dataset_name === 'trading_calendars' || report.dataset_name === 'calendars') {
    return {
      label: '同步日历',
      to: '/data-system/sync-tasks',
      search: { focus: 'calendars' },
    };
  }

  return undefined;
}

export function getClosedLoopStatus(coverage?: DatabaseCoverageSummary) {
  if (isCoverageDegraded(coverage)) {
    return {
      color: 'warning',
      label: '覆盖率待确认',
      title: '日线覆盖率暂不可确认',
      description: coverage?.coverage_message ?? 'Parquet / DuckDB 查询暂不可用，股票池和交易日历仍可查看。',
    };
  }

  if (!coverage || coverage.stock_pool_total <= 0) {
    return {
      color: 'default',
      label: '待同步股票池',
      title: '还没有可判断的 A 股股票池',
      description: '先同步股票池和交易日历，再判断日线覆盖率和补数范围。',
    };
  }

  if (!coverage.calendar_latest_date || !coverage.coverage_start_date || !coverage.coverage_end_date) {
    return {
      color: 'warning',
      label: '待补交易日历',
      title: '交易日历覆盖不足',
      description: '日线缺口需要依赖交易日历判断，建议先补齐 A 股交易日历。',
    };
  }

  if (coverage.daily_missing_symbol_days > 0) {
    return {
      color: 'warning',
      label: '需要补日线',
      title: `日线只覆盖 ${formatNumber(coverage.daily_covered_stock_count)}/${formatNumber(coverage.stock_pool_total)} 只股票`,
      description: `最近半年缺少 ${formatNumber(coverage.daily_missing_symbol_days)} 个股票-交易日，建议创建市场级日线缺口补齐任务。`,
    };
  }

  return {
    color: 'green',
    label: '数据闭环正常',
    title: '股票池、交易日历和日线覆盖已对齐',
    description: '当前没有检测到待补股票-交易日，可以继续保持收盘后增量同步。',
  };
}

export function getRepairFocus(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
  const hasRepairRange =
    Boolean(watermark.repair_start_date && watermark.repair_end_date) ||
    (isMarketDailyRepairHint(watermark) && Boolean(coverage?.coverage_start_date && coverage.coverage_end_date));
  if (!hasRepairRange) {
    return undefined;
  }
  if (watermark.dataset_name === 'daily_bars') {
    return !watermark.symbol || isMarketDailyRepairHint(watermark) ? 'daily-bars-market-repair' : 'daily-bars';
  }
  if (watermark.dataset_name === 'calendars' || watermark.dataset_name === 'trading_calendars') {
    return 'calendars';
  }
  if (watermark.dataset_name === 'stocks' || watermark.dataset_name === 'stock_list') {
    return 'stock-list';
  }
  return undefined;
}

export function getRepairSearch(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
  const focus = getRepairFocus(watermark, coverage);
  return {
    focus,
    market: watermark.market ?? coverage?.market ?? undefined,
    symbol: focus === 'daily-bars' ? watermark.symbol ?? undefined : undefined,
    startDate: watermark.repair_start_date ?? coverage?.coverage_start_date ?? undefined,
    endDate: watermark.repair_end_date ?? coverage?.coverage_end_date ?? undefined,
    syncSource: watermark.requested_source || watermark.source || undefined,
    maxSymbols: focus === 'daily-bars-market-repair' ? DEFAULT_MARKET_REPAIR_MAX_SYMBOLS : undefined,
  };
}

export function formatDatabaseRole(role?: string) {
  if (role === 'local_fallback') {
    return '本地开发备用';
  }
  if (role === 'metadata_store') {
    return '元数据库连接';
  }
  return '元数据库';
}

export function formatDuckDbEngineStatus(status?: string) {
  if (status === 'available') {
    return '可用';
  }
  if (status === 'unavailable') {
    return '不可用';
  }
  return '未知';
}

export function getDuckDbEngineStatusColor(status?: string) {
  if (status === 'available') {
    return 'green';
  }
  if (status === 'unavailable') {
    return 'warning';
  }
  return 'default';
}


export function getNumericRecordId(value?: string | number | null) {
  const recordId = Number(value);
  return Number.isFinite(recordId) && recordId > 0 ? recordId : undefined;
}

export function getNumericTaskId(value?: string | number | null) {
  return getNumericRecordId(value);
}

export function scrollToLineageSection() {
  window.setTimeout(() => {
    document.getElementById('database-lineage-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 80);
}

