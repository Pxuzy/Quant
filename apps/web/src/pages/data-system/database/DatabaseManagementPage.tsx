import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import {
  CalendarOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  ProfileOutlined,
  ReloadOutlined,
  StockOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import {
  useDataQualityCheckRunsQuery,
  useDataQualityOverviewQuery,
  useDataQualityReportsQuery,
  useRunDataQualityCheckMutation,
} from '../../../features/data-quality/api';
import type { DataQualityReport, DataQualityReportListParams } from '../../../features/data-quality/types';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import type {
  DataSource,
  DataSourceCapability,
  DataSourceProviderMetadata,
  DataSourceSmokeSummary,
} from '../../../features/data-sources/types';
import { useDatabaseIntegrationOverviewQuery, useDatabaseLineageQuery, useDatabaseStatusQuery } from '../../../features/database/api';
import type {
  DatabaseCoverageSummary,
  DatabaseIntegrationOverview,
  DatabaseLineageItem,
  DatabaseLineageParams,
  DatasetSnapshot,
  ProviderIntegration,
  RecentIngestBatch,
  SyncWatermark,
} from '../../../features/database/types';
import { useDatasetsQuery } from '../../../features/datasets/api';
import type { Dataset } from '../../../features/datasets/types';
import { useTradingCalendarsQuery } from '../../../features/trading-calendars/api';
import type { TradingCalendarDay } from '../../../features/trading-calendars/types';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatBytes, formatDate, formatDateTime, formatNumber, formatPercent } from '../../../shared/components/formatters';
import {
  formatCapability,
  formatAuthMode,
  formatExchange,
  formatLayer,
  formatMarket,
  formatProviderType,
  formatQualityCheckType,
  formatStability,
  formatStorageType,
  formatTaskType,
  aShareMarketOptions,
} from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

const FIRST_PAGE = 1;
const DATASET_PAGE_SIZE = 8;
const CALENDAR_PAGE_SIZE = 8;
const REPORT_PAGE_SIZE = 8;
const LINEAGE_PAGE_SIZE = 8;
const DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20;
const DEFAULT_MARKET = 'A_SHARE';
const V1_DATA_SOURCE_CODES = new Set(['akshare', 'baostock', 'adata', 'tushare', 'stock_sdk']);

const databaseMarketOptions = aShareMarketOptions;

const lineageDatasetOptions = [
  { label: '全部数据集', value: '' },
  { label: '日线行情', value: 'daily_bars' },
  { label: '股票池', value: 'stocks' },
  { label: '交易日历', value: 'trading_calendars' },
];

const lineageStatusOptions = [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '运行中', value: 'running' },
];

const qualityStatusOptions = [
  { label: '全部状态', value: '' },
  { label: '通过', value: 'good' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' },
];

const qualitySeverityOptions = [
  { label: '全部级别', value: '' },
  { label: '信息', value: 'info' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' },
];

type DatasetMetricSource = Pick<Dataset, 'latest_data_date' | 'row_count' | 'storage_type'>;
type FreshnessDatasetName = 'stocks' | 'daily_bars' | 'trading_calendars';

type FreshnessItem = {
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

type RepairSearch = {
  focus?: string;
  market?: string;
  symbol?: string;
  startDate?: string;
  endDate?: string;
  syncSource?: string;
  maxSymbols?: number;
};

type QualityAction = {
  label: string;
  to: '/data-system/sync-tasks' | '/data-system/stocks' | '/data-system/database';
  search?: RepairSearch | { qualityDatasetName?: string; qualityPage?: number; qualityPageSize?: number };
};

type CalendarCoverageStats = {
  coverageStart?: string | null;
  coverageEnd?: string | null;
  latestDate?: string | null;
  loadedStart?: string | null;
  loadedEnd?: string | null;
  loadedTotal: number;
  loadedOpenDays: number;
  loadedClosedDays: number;
};

type LineageFilterValues = {
  batchId?: number;
  datasetName?: string;
  symbol?: string;
  tradeDate?: Dayjs;
  source?: string;
  status?: string;
};

type TraceQualityReportBatch = (report: DataQualityReport) => void;

function getLatestDatasetDate(datasets: DatasetMetricSource[]) {
  const dates = datasets
    .map((dataset) => dataset.latest_data_date)
    .filter((date): date is string => Boolean(date))
    .sort();
  return dates[dates.length - 1];
}

function getDatasetStorageSummary(datasets: DatasetMetricSource[]) {
  return datasets.reduce<Record<string, number>>((summary, dataset) => {
    const storageType = dataset.storage_type || 'unknown';
    summary[storageType] = (summary[storageType] ?? 0) + 1;
    return summary;
  }, {});
}

function getDatasetRowsTotal(datasets: DatasetMetricSource[]) {
  return datasets.reduce((sum, dataset) => sum + (dataset.row_count ?? 0), 0);
}

function getDatasetSnapshotByName(snapshots: DatasetSnapshot[], datasetName: string) {
  return snapshots.find((snapshot) => snapshot.dataset_name === datasetName);
}

function getSourceCapabilities(source: DataSource): DataSourceCapability {
  return source.capabilities ?? source.config_json?.capabilities ?? {};
}

function getSourceMetadata(source: DataSource): DataSourceProviderMetadata {
  return source.provider_metadata ?? source.config_json?.provider_metadata ?? {};
}

function getSourceLastSmoke(source: DataSource): DataSourceSmokeSummary | undefined {
  return source.config_json?.last_smoke_test;
}

function formatSourceHealthMessage(source: DataSource) {
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

function formatCapabilitySummary(capabilities: DataSourceCapability) {
  const items = [
    capabilities.stock_list ? formatCapability('stock_list') : null,
    capabilities.daily_bars ? formatCapability('daily_bars') : null,
    capabilities.calendars ? formatCapability('calendars') : null,
  ].filter(Boolean);

  return items.length ? items.join(' / ') : '未声明核心能力';
}

function formatDailyBarExchanges(capabilities: DataSourceCapability) {
  if (!capabilities.daily_bars) {
    return '不提供日线';
  }
  const exchanges = capabilities.daily_bar_exchanges;
  if (!Array.isArray(exchanges) || exchanges.length === 0) {
    return '日线交易所未声明';
  }
  return exchanges.map((exchange) => formatExchange(exchange)).join(' / ');
}

function formatSmokeSample(sample?: Array<Record<string, unknown>>) {
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

function getDateRange(dates: string[]) {
  const sortedDates = [...dates].sort();
  return {
    start: sortedDates[0],
    end: sortedDates[sortedDates.length - 1],
  };
}

function getCalendarCoverageStats(
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

function getDatasetFreshnessItems(snapshots: DatasetSnapshot[]): FreshnessItem[] {
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

function getFreshnessTagColor(item: FreshnessItem) {
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

function getMetadataStoreLabel(kind?: string) {
  if (!kind || kind === '-') {
    return '-';
  }
  if (kind === 'SQLite') {
    return 'SQLite 本地备用';
  }
  if (kind === 'PostgreSQL') {
    return 'PostgreSQL 元数据库';
  }
  return `${kind} 元数据库`;
}

function formatRange(start?: string | null, end?: string | null) {
  if (!start && !end) {
    return '-';
  }
  if (start && end && start !== end) {
    return `${formatDate(start)} ~ ${formatDate(end)}`;
  }
  return formatDate(end || start);
}

function formatWatermarkScope(watermark: SyncWatermark) {
  const market = formatMarket(watermark.market);
  return watermark.symbol ? `${market} / ${watermark.symbol}` : market;
}

function formatRepairRange(watermark: SyncWatermark) {
  return formatRange(watermark.repair_start_date, watermark.repair_end_date);
}

function getDailyCompletenessPercent(coverage?: DatabaseCoverageSummary) {
  if (coverage?.daily_completeness === undefined || coverage.daily_completeness === null) {
    return undefined;
  }
  return coverage.daily_completeness * 100;
}

function isCoverageDegraded(coverage?: DatabaseCoverageSummary) {
  return coverage?.coverage_status === 'degraded';
}

function findRepairableDailyWatermark(watermarks: SyncWatermark[]) {
  return watermarks.find((watermark) => watermark.dataset_name === 'daily_bars' && Boolean(watermark.repair_reason));
}

function isMarketDailyRepairHint(watermark: SyncWatermark) {
  return watermark.dataset_name === 'daily_bars' && watermark.repair_reason?.includes('该市场同区间日线');
}

function getMarketRepairSearch(coverage?: DatabaseCoverageSummary, watermark?: SyncWatermark): RepairSearch {
  return {
    focus: 'daily-bars-market-repair',
    market: watermark?.market ?? coverage?.market,
    startDate: watermark?.repair_start_date ?? coverage?.coverage_start_date ?? undefined,
    endDate: watermark?.repair_end_date ?? coverage?.coverage_end_date ?? undefined,
    syncSource: watermark?.requested_source || watermark?.source || undefined,
    maxSymbols: DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
  };
}

function getQualityReportAction(report: DataQualityReport, coverage?: DatabaseCoverageSummary): QualityAction | undefined {
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

function getClosedLoopStatus(coverage?: DatabaseCoverageSummary) {
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

function getRepairFocus(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
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

function getRepairSearch(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
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

function formatDatabaseRole(role?: string) {
  if (role === 'local_fallback') {
    return '本地开发备用';
  }
  if (role === 'metadata_store') {
    return '元数据库连接';
  }
  return '元数据库';
}

function formatDuckDbEngineStatus(status?: string) {
  if (status === 'available') {
    return '可用';
  }
  if (status === 'unavailable') {
    return '不可用';
  }
  return '未知';
}

function getDuckDbEngineStatusColor(status?: string) {
  if (status === 'available') {
    return 'green';
  }
  if (status === 'unavailable') {
    return 'warning';
  }
  return 'default';
}

function buildDatasetColumns(): ColumnsType<Dataset> {
  return [
    {
      title: '数据内容',
      dataIndex: 'name',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{formatCapability(record.name)}</Typography.Text>
          <Typography.Text type="secondary">{record.name}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '数据层级',
      dataIndex: 'layer',
      width: 120,
      render: (value) => <Tag>{formatLayer(value)}</Tag>,
    },
    {
      title: '主存储介质',
      dataIndex: 'storage_type',
      width: 130,
      render: (value) => <Tag color="blue">{formatStorageType(value)}</Tag>,
    },
    {
      title: '记录数',
      dataIndex: 'row_count',
      width: 130,
      render: (value) => formatNumber(value),
    },
    {
      title: '最新日期',
      dataIndex: 'latest_data_date',
      width: 140,
      render: (value) => formatDate(value),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 110,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (value) => formatDateTime(value),
    },
  ];
}

function buildSnapshotColumns(): ColumnsType<DatasetSnapshot> {
  return [
    {
      title: '数据集快照',
      dataIndex: 'dataset_name',
      width: 190,
      render: (_, snapshot) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{formatCapability(snapshot.dataset_name)}</Typography.Text>
          <Typography.Text type="secondary">{snapshot.dataset_version}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '来源/层级',
      dataIndex: 'source',
      width: 160,
      render: (_, snapshot) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{snapshot.source}</Typography.Text>
          <Typography.Text type="secondary">
            {formatLayer(snapshot.layer)} / {formatStorageType(snapshot.storage_type)}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '记录数',
      dataIndex: 'row_count',
      width: 110,
      render: (value) => formatNumber(value),
    },
    {
      title: '最新日期',
      dataIndex: 'latest_data_date',
      width: 130,
      render: (value) => formatDate(value),
    },
    {
      title: '契约',
      dataIndex: 'schema_fields_count',
      width: 180,
      render: (_, snapshot) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatNumber(snapshot.schema_fields_count)} 个字段</Typography.Text>
          <Typography.Text type="secondary">主键 {snapshot.primary_keys_json.join(', ') || '-'}</Typography.Text>
          <Typography.Text type="secondary">分区 {snapshot.partition_keys_json.join(', ') || '-'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 100,
      render: (value) => <StatusTag value={value} />,
    },
  ];
}

function getNumericRecordId(value?: string | number | null) {
  const recordId = Number(value);
  return Number.isFinite(recordId) && recordId > 0 ? recordId : undefined;
}

function getNumericTaskId(value?: string | number | null) {
  return getNumericRecordId(value);
}

function scrollToLineageSection() {
  window.setTimeout(() => {
    document.getElementById('database-lineage-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 80);
}

function buildWatermarkColumns(coverage?: DatabaseCoverageSummary): ColumnsType<SyncWatermark> {
  return [
    {
      title: '数据类型',
      dataIndex: 'dataset_name',
      width: 130,
      render: (value) => <Typography.Text strong>{formatCapability(value)}</Typography.Text>,
    },
    {
      title: '范围',
      width: 150,
      render: (_, watermark) => formatWatermarkScope(watermark),
    },
    {
      title: '实际来源',
      dataIndex: 'source',
      width: 150,
      render: (_, watermark) => (
        <Space direction="vertical" size={0}>
          <Tag color="blue">{watermark.source}</Tag>
          <Typography.Text type="secondary">请求 {watermark.requested_source || '-'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '最新成功日期',
      dataIndex: 'latest_success_date',
      width: 130,
      render: (value) => formatDate(value),
    },
    {
      title: '待补范围',
      width: 190,
      render: (_, watermark) =>
        watermark.repair_start_date || watermark.repair_end_date ? (
          <Space direction="vertical" size={0}>
            <Typography.Text>{formatRepairRange(watermark)}</Typography.Text>
            <Typography.Text type="secondary" ellipsis title={watermark.repair_reason ?? undefined}>
              {watermark.repair_reason ?? '建议补齐缺口'}
            </Typography.Text>
          </Space>
        ) : (
          <Typography.Text type="secondary">{watermark.repair_reason ?? '暂无建议'}</Typography.Text>
        ),
    },
    {
      title: '最近失败',
      width: 190,
      render: (_, watermark) =>
        watermark.last_failed_at || watermark.last_failure_reason ? (
          <Space direction="vertical" size={0}>
            <Typography.Text type="danger">{formatDateTime(watermark.last_failed_at)}</Typography.Text>
            {watermark.last_failure_batch_id ? (
              <Typography.Text type="secondary">失败批次 #{watermark.last_failure_batch_id}</Typography.Text>
            ) : null}
            <Typography.Text type="secondary" ellipsis title={watermark.last_failure_reason ?? undefined}>
              {watermark.last_failure_reason ?? '未记录原因'}
            </Typography.Text>
          </Space>
        ) : (
          <Typography.Text type="secondary">无</Typography.Text>
        ),
    },
    {
      title: '写入',
      dataIndex: 'records_written',
      width: 100,
      render: (value) => formatNumber(value),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 100,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '最近成功',
      dataIndex: 'last_success_at',
      width: 170,
      render: (_, watermark) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatDateTime(watermark.last_success_at)}</Typography.Text>
          <Typography.Text type="secondary">成功批次 #{watermark.batch_id}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 150,
      render: (_, watermark) => {
        const taskId = getNumericTaskId(watermark.task_id);
        const failureTaskId = getNumericTaskId(watermark.last_failure_task_id);
        const focus = getRepairFocus(watermark, coverage);
        return (
          <Space size={2}>
            {taskId ? (
              <Link to="/data-system/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small" icon={<ProfileOutlined />}>
                  任务
                </Button>
              </Link>
            ) : null}
            {failureTaskId ? (
              <Link to="/data-system/sync-tasks" search={{ taskId: failureTaskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small">
                  失败
                </Button>
              </Link>
            ) : null}
            {focus ? (
              <Link to="/data-system/sync-tasks" search={getRepairSearch(watermark, coverage)}>
                <Button type="link" size="small" icon={<CloudSyncOutlined />}>
                  补数
                </Button>
              </Link>
            ) : null}
          </Space>
        );
      },
    },
  ];
}

function buildProviderColumns(): ColumnsType<ProviderIntegration> {
  return [
    {
      title: '数据源',
      dataIndex: 'source',
      width: 120,
      render: (value) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: '尝试/成功/失败',
      width: 150,
      render: (_, provider) => `${formatNumber(provider.attempts)} / ${formatNumber(provider.successes)} / ${formatNumber(provider.failures)}`,
    },
    {
      title: '自动降级写入',
      dataIndex: 'fallback_successes',
      width: 130,
      render: (value) => <Tag color={value > 0 ? 'green' : 'default'}>{formatNumber(value)}</Tag>,
    },
    {
      title: '写入行数',
      dataIndex: 'records_written',
      width: 120,
      render: (value) => formatNumber(value),
    },
    {
      title: '最近成功',
      dataIndex: 'last_success_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
    {
      title: '最近失败',
      dataIndex: 'last_failure_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
  ];
}

function buildProviderStatusColumns(): ColumnsType<DataSource> {
  return [
    {
      title: 'Provider',
      dataIndex: 'code',
      width: 150,
      render: (_, source) => {
        const metadata = getSourceMetadata(source);
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[6, 4]}>
              <Typography.Text strong>{source.name}</Typography.Text>
              <Typography.Text type="secondary">{source.code}</Typography.Text>
            </Space>
            <Space wrap size={[4, 4]}>
              <Tag color="geekblue">{formatProviderType(metadata.provider_type ?? 'external_api')}</Tag>
              <Tag>{formatStability(metadata.stability ?? 'community')}</Tag>
            </Space>
          </Space>
        );
      },
    },
    {
      title: '健康/启用',
      width: 150,
      render: (_, source) => (
        <Space direction="vertical" size={2}>
          <Space wrap size={[4, 4]}>
            <StatusTag value={source.health_status} />
            <Tag color={source.enabled ? 'green' : 'default'}>{source.enabled ? '已启用' : '已禁用'}</Tag>
          </Space>
          <Typography.Text type="secondary">最近检查 {formatDateTime(source.last_checked_at)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '能力声明',
      width: 210,
      render: (_, source) => {
        const capabilities = getSourceCapabilities(source);
        return (
          <Space direction="vertical" size={2}>
            <Typography.Text>{formatCapabilitySummary(capabilities)}</Typography.Text>
            <Typography.Text type="secondary">日线覆盖 {formatDailyBarExchanges(capabilities)}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: '接入信息',
      width: 220,
      render: (_, source) => {
        const metadata = getSourceMetadata(source);
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[4, 4]}>
              <Tag color={source.requires_token ? 'warning' : 'blue'}>
                {formatAuthMode(metadata.auth_mode ?? (source.requires_token ? 'token' : 'none'))}
              </Tag>
              <Tag>优先级 {formatNumber(source.priority)}</Tag>
            </Space>
            <Typography.Text type="secondary" ellipsis title={metadata.install_note ?? undefined}>
              {metadata.install_note || '无额外安装说明'}
            </Typography.Text>
          </Space>
        );
      },
    },
    {
      title: '最近真实取样',
      width: 260,
      render: (_, source) => {
        const lastSmoke = getSourceLastSmoke(source);
        if (!lastSmoke) {
          return (
            <Space direction="vertical" size={2}>
              <Typography.Text type="secondary">尚未取样</Typography.Text>
              <Typography.Text type="secondary">{formatSourceHealthMessage(source)}</Typography.Text>
            </Space>
          );
        }
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[4, 4]}>
              <Tag>{formatCapability(lastSmoke.capability)}</Tag>
              <StatusTag value={lastSmoke.status} />
              <Tag>
                原始 {formatNumber(lastSmoke.raw_records)} / 标准化 {formatNumber(lastSmoke.normalized_records)}
              </Tag>
            </Space>
            <Typography.Text type="secondary" ellipsis title={formatSmokeSample(lastSmoke.sample)}>
              {formatSmokeSample(lastSmoke.sample)}
            </Typography.Text>
          </Space>
        );
      },
    },
  ];
}

function buildBatchColumns(onTraceBatch?: (batch: RecentIngestBatch) => void): ColumnsType<RecentIngestBatch> {
  return [
    {
      title: '批次',
      dataIndex: 'id',
      width: 100,
      render: (value) => <Typography.Text code>#{value}</Typography.Text>,
    },
    {
      title: '数据类型',
      dataIndex: 'dataset_name',
      width: 130,
      render: (value) => formatCapability(value),
    },
    {
      title: '来源',
      width: 150,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{batch.source}</Typography.Text>
          <Typography.Text type="secondary">请求 {batch.requested_source}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '范围',
      width: 180,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatRange(batch.start_date, batch.end_date)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(batch.market)}
            {batch.symbol ? ` / ${batch.symbol}` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '版本',
      width: 130,
      render: (_, batch) => `${batch.schema_version} / ${batch.normalize_version}`,
    },
    {
      title: '写入',
      dataIndex: 'records_written',
      width: 100,
      render: (value) => formatNumber(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <StatusTag value={batch.status} />
          <Typography.Text type="secondary">{batch.quality_status}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '完成时间',
      dataIndex: 'finished_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 150,
      render: (_, batch) => {
        const taskId = getNumericTaskId(batch.task_id);
        return (
          <Space size={2}>
            {taskId ? (
              <Link to="/data-system/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small" icon={<ProfileOutlined />}>
                  任务
                </Button>
              </Link>
            ) : null}
            {batch.dataset_name === 'daily_bars' && batch.symbol ? (
              <Link to="/data-system/stocks/$symbol" params={{ symbol: batch.symbol }}>
                <Button type="link" size="small" icon={<StockOutlined />}>
                  股票
                </Button>
              </Link>
            ) : null}
            <Button type="link" size="small" onClick={() => onTraceBatch?.(batch)}>
              血缘
            </Button>
            {!taskId && !(batch.dataset_name === 'daily_bars' && batch.symbol) ? '-' : null}
          </Space>
        );
      },
    },
  ];
}

function buildLineageColumns(): ColumnsType<DatabaseLineageItem> {
  return [
    {
      title: '批次',
      dataIndex: 'id',
      width: 96,
      render: (value, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text code>#{value}</Typography.Text>
          <StatusTag value={item.status} />
        </Space>
      ),
    },
    {
      title: '写入对象',
      width: 190,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{formatCapability(item.dataset_name)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(item.market)}
            {item.symbol ? ` / ${item.symbol}` : ''}
          </Typography.Text>
          <Typography.Text type="secondary">{formatRange(item.start_date, item.end_date)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '来源链路',
      width: 180,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>
            请求 {item.requested_source} 到实际 {item.source}
          </Typography.Text>
          <Typography.Text type="secondary">
            任务 {formatTaskType(item.task_type)} / {item.task_source}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '处理版本',
      width: 160,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>Schema {item.schema_version}</Typography.Text>
          <Typography.Text type="secondary">Normalize {item.normalize_version}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '记录数',
      width: 160,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>写入 {formatNumber(item.records_written)}</Typography.Text>
          <Typography.Text type="secondary">
            原始 {formatNumber(item.raw_records)} / 标准化 {formatNumber(item.normalized_records)}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 110,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '执行时间',
      width: 190,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatDateTime(item.started_at)}</Typography.Text>
          <Typography.Text type="secondary">完成 {formatDateTime(item.finished_at)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '错误',
      width: 190,
      render: (_, item) => {
        const message = item.error_message || item.task_error_message || item.validation_errors_json?.[0];
        return message ? (
          <Typography.Text type="danger" ellipsis title={message}>
            {message}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">无</Typography.Text>
        );
      },
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 150,
      render: (_, item) => {
        const taskId = getNumericTaskId(item.task_id);
        return (
          <Space size={2}>
            {taskId ? (
              <Link to="/data-system/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small" icon={<ProfileOutlined />}>
                  任务
                </Button>
              </Link>
            ) : null}
            {item.dataset_name === 'daily_bars' && item.symbol ? (
              <Link to="/data-system/stocks/$symbol" params={{ symbol: item.symbol }}>
                <Button type="link" size="small" icon={<StockOutlined />}>
                  股票
                </Button>
              </Link>
            ) : null}
          </Space>
        );
      },
    },
  ];
}

function buildReportColumns(
  coverage?: DatabaseCoverageSummary,
  onTraceBatch?: TraceQualityReportBatch,
): ColumnsType<DataQualityReport> {
  return [
    {
      title: '数据集',
      dataIndex: 'dataset_name',
      width: 150,
      render: (value) => <Typography.Text strong>{formatCapability(value)}</Typography.Text>,
    },
    {
      title: '检查项',
      dataIndex: 'check_type',
      width: 150,
      render: (value) => formatQualityCheckType(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 96,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 100,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '指标',
      width: 220,
      render: (_, report) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{report.metric_name}</Typography.Text>
          <Typography.Text type="secondary">
            实际 {report.metric_value ?? '-'} / 期望 {report.expected_value ?? '-'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '说明',
      dataIndex: 'message',
      render: (value) => <Typography.Text>{value}</Typography.Text>,
    },
    {
      title: '回溯',
      key: 'trace',
      width: 260,
      render: (_, report) => {
        const trace = report.trace;
        if (!trace) {
          return <Typography.Text type="secondary">暂无批次记录</Typography.Text>;
        }
        const taskId = getNumericTaskId(trace.latest_task_id);
        const batchId = getNumericRecordId(trace.latest_batch_id);
        const batchLabel = trace.latest_batch_id ? `批次 #${trace.latest_batch_id}` : '暂无批次';
        const sourceLabel = trace.latest_batch_source || trace.dataset_source || '-';
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[6, 4]}>
              <Tag color="blue">来源 {sourceLabel}</Tag>
              <Tag>{formatStorageType(trace.storage_type || '-')}</Tag>
              <Tag>{formatNumber(trace.row_count ?? 0)} 行</Tag>
            </Space>
            <Typography.Text type="secondary">
              Schema {formatNumber(trace.schema_fields_count ?? 0)} 字段 / 主键 {trace.primary_keys_json?.join(', ') || '-'}
            </Typography.Text>
            <Space wrap size={[6, 4]}>
              <Typography.Text type="secondary">
                {batchLabel}
                {trace.latest_batch_schema_version || trace.latest_batch_normalize_version
                  ? ` / ${trace.latest_batch_schema_version || '-'} / ${trace.latest_batch_normalize_version || '-'}`
                  : ''}
              </Typography.Text>
              {taskId ? (
                <Link to="/data-system/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                  <Button type="link" size="small" icon={<ProfileOutlined />}>
                    任务
                  </Button>
                </Link>
              ) : null}
              {batchId && onTraceBatch ? (
                <Button type="link" size="small" icon={<FileSearchOutlined />} onClick={() => onTraceBatch(report)}>
                  血缘
                </Button>
              ) : null}
            </Space>
          </Space>
        );
      },
    },
    {
      title: '检查时间',
      dataIndex: 'checked_at',
      width: 180,
      render: (value) => formatDateTime(value),
    },
    {
      title: '治理',
      key: 'action',
      fixed: 'right',
      width: 120,
      render: (_, report) => {
        const action = getQualityReportAction(report, coverage);
        return action ? (
          <Link to={action.to} search={action.search}>
            <Button type="link" size="small" icon={<CloudSyncOutlined />}>
              {action.label}
            </Button>
          </Link>
        ) : (
          <Typography.Text type="secondary">查看说明</Typography.Text>
        );
      },
    },
  ];
}

function DataClosedLoopPanel({
  overview,
  loading,
  error,
}: {
  overview?: DatabaseIntegrationOverview;
  loading: boolean;
  error: boolean;
}) {
  if (error) {
    return <Alert type="error" showIcon message="数据闭环状态加载失败" description="后端数据整合总览接口暂不可用。" />;
  }

  if (loading) {
    return (
      <Card className="database-panel database-closed-loop-card">
        <Skeleton active paragraph={{ rows: 3 }} />
      </Card>
    );
  }

  const coverage = overview?.coverage_summary;
  const summary = overview?.summary;
  const watermarks = overview?.sync_watermarks ?? [];
  const repairableDailyWatermark = findRepairableDailyWatermark(watermarks);
  const closedLoop = getClosedLoopStatus(coverage);
  const completeness = getDailyCompletenessPercent(coverage);
  const repairSearch = getMarketRepairSearch(coverage, repairableDailyWatermark);
  const coverageDegraded = isCoverageDegraded(coverage);
  const hasDailyGap = Boolean(coverage && !coverageDegraded && coverage.daily_missing_symbol_days > 0);

  return (
    <Card id="database-closed-loop-section" className="database-panel database-closed-loop-card">
      <div className="database-closed-loop">
        <div className="database-closed-loop-main">
          <Space direction="vertical" size={10}>
            <Space wrap size={[8, 8]}>
              <Tag color={closedLoop.color}>{closedLoop.label}</Tag>
              <Tag>{formatMarket(coverage?.market, '中国 A 股')}</Tag>
            </Space>
            <div>
              <Typography.Title level={4}>{closedLoop.title}</Typography.Title>
              <Typography.Text type="secondary">{closedLoop.description}</Typography.Text>
            </div>
            <Space wrap size={[10, 8]}>
              {hasDailyGap ? (
                <Link to="/data-system/sync-tasks" search={repairSearch}>
                  <Button type="primary" icon={<CloudSyncOutlined />}>
                    创建市场级补齐任务
                  </Button>
                </Link>
              ) : null}
              <Link to="/data-system/sync-tasks">
                <Button icon={<ProfileOutlined />}>查看同步调度</Button>
              </Link>
            </Space>
          </Space>
        </div>
        <div className="database-closed-loop-metrics">
          <div>
            <Typography.Text type="secondary">股票池</Typography.Text>
            <Typography.Title level={4}>{formatNumber(coverage?.stock_pool_total ?? 0)} 只</Typography.Title>
            <Typography.Text type="secondary">有日线 {formatNumber(coverage?.daily_covered_stock_count ?? 0)} 只</Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">日线完整度</Typography.Text>
            <Typography.Title level={4}>{formatPercent(completeness)}</Typography.Title>
            <Typography.Text type="secondary">
              {coverageDegraded
                ? '等待 Parquet / DuckDB 查询恢复'
                : `${formatNumber(coverage?.daily_actual_symbol_days ?? 0)} / ${formatNumber(coverage?.daily_expected_symbol_days ?? 0)}`}
            </Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">{coverageDegraded ? '覆盖率状态' : '待补股票-交易日'}</Typography.Text>
            <Typography.Title level={4}>{formatNumber(coverage?.daily_missing_symbol_days ?? 0)}</Typography.Title>
            <Typography.Text type="secondary">
              {coverageDegraded ? '暂不可确认' : formatRange(coverage?.coverage_start_date, coverage?.coverage_end_date)}
            </Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">最近入库批次</Typography.Text>
            <Typography.Title level={4}>{formatNumber(summary?.recent_batches_total ?? 0)} 个</Typography.Title>
            <Typography.Text type="secondary">失败 {formatNumber(summary?.failed_batches_total ?? 0)} 个</Typography.Text>
          </div>
        </div>
      </div>
    </Card>
  );
}

function CoverageSummaryPanel({
  coverage,
  loading,
  error,
}: {
  coverage?: DatabaseCoverageSummary;
  loading: boolean;
  error: boolean;
}) {
  if (error) {
    return <Alert type="error" showIcon message="覆盖率摘要加载失败" description="后端数据整合总览接口暂不可用。" />;
  }

  if (loading) {
    return <Skeleton active paragraph={{ rows: 3 }} />;
  }

  if (!coverage) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无覆盖率摘要" />;
  }

  const completeness =
    coverage.daily_completeness === undefined || coverage.daily_completeness === null
      ? undefined
      : coverage.daily_completeness * 100;
  const coverageDegraded = isCoverageDegraded(coverage);
  const hasDailyGap = !coverageDegraded && coverage.daily_missing_symbol_days > 0;
  return (
    <Space className="database-coverage-stack" direction="vertical" size={12}>
      {coverageDegraded ? (
        <Alert
          type="warning"
          showIcon
          message="覆盖率暂不可确认"
          description={coverage.coverage_message ?? 'Parquet / DuckDB 覆盖率查询失败，当前覆盖率按未知处理。'}
        />
      ) : null}
      <div className="database-coverage-grid">
        <div className="database-coverage-item">
          <Typography.Text type="secondary">股票池覆盖</Typography.Text>
          <Typography.Title level={4}>{formatNumber(coverage.stock_pool_total)} 只</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag color="blue">{formatMarket(coverage.market)}</Tag>
            <Tag>有日线 {formatNumber(coverage.daily_covered_stock_count)} 只</Tag>
          </Space>
        </div>
        <div className="database-coverage-item">
          <Typography.Text type="secondary">交易日历覆盖</Typography.Text>
          <Typography.Title level={4}>{formatRange(coverage.coverage_start_date, coverage.coverage_end_date)}</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag color="cyan">最新 {formatDate(coverage.calendar_latest_date)}</Tag>
            <Tag>{formatMarket(coverage.market)}</Tag>
          </Space>
        </div>
        <div className="database-coverage-item">
          <Typography.Text type="secondary">日线完整度</Typography.Text>
          <Typography.Title level={4}>{formatPercent(completeness)}</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag>应有 {formatNumber(coverage.daily_expected_symbol_days)}</Tag>
            <Tag color={coverageDegraded ? 'warning' : 'green'}>
              {coverageDegraded ? '已有暂不可确认' : `已有 ${formatNumber(coverage.daily_actual_symbol_days)}`}
            </Tag>
          </Space>
        </div>
        <div className="database-coverage-item">
          <Typography.Text type="secondary">{coverageDegraded ? '覆盖率状态' : '缺失股票-交易日'}</Typography.Text>
          <Typography.Title level={4}>{formatNumber(coverage.daily_missing_symbol_days)}</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag color={coverageDegraded ? 'warning' : hasDailyGap ? 'warning' : 'green'}>
              {coverageDegraded ? '暂不可确认' : '待补数据'}
            </Tag>
            <Tag>按股票 x 开市日统计</Tag>
          </Space>
        </div>
      </div>
      {hasDailyGap ? (
        <Alert
          type="warning"
          showIcon
          message="检测到市场级日线缺口"
          description={`建议从同步调度创建市场级日线缺口补齐任务，范围 ${formatRange(coverage.coverage_start_date, coverage.coverage_end_date)}（最近半年）。`}
          action={
            <Link to="/data-system/sync-tasks" search={getMarketRepairSearch(coverage)}>
              <Button size="small" type="primary">
                去补齐日线
              </Button>
            </Link>
          }
        />
      ) : null}
    </Space>
  );
}

function DataFreshnessPanel({
  snapshots,
  loading,
  error,
}: {
  snapshots: DatasetSnapshot[];
  loading: boolean;
  error: boolean;
}) {
  if (error) {
    return <Alert type="error" showIcon message="数据新鲜度加载失败" description="后端数据整合总览接口暂不可用。" />;
  }

  if (loading) {
    return <Skeleton active paragraph={{ rows: 3 }} />;
  }

  const items = getDatasetFreshnessItems(snapshots);
  return (
    <div className="database-freshness-grid">
      {items.map((item) => (
        <div className="database-freshness-item" key={item.datasetName}>
          <div className="database-freshness-head">
            <Space direction="vertical" size={0}>
              <Typography.Text strong>{item.title}</Typography.Text>
              <Typography.Text type="secondary">{item.description}</Typography.Text>
            </Space>
            <StatusTag value={item.qualityStatus} />
          </div>
          <div className="database-freshness-date">
            <Typography.Text type="secondary">最新日期</Typography.Text>
            <Typography.Title level={4}>{formatDate(item.latestDate)}</Typography.Title>
          </div>
          <Space wrap size={[6, 6]}>
            <Tag color={getFreshnessTagColor(item)}>{item.latestDate ? '已有数据' : '待同步'}</Tag>
            <Tag>{formatStorageType(item.storageType || '-')}</Tag>
            <Tag>{formatNumber(item.rowCount)} 行</Tag>
            <Tag color="blue">来源 {item.source || '-'}</Tag>
          </Space>
          <Link to={item.actionPath} search={item.actionSearch}>
            <Button type="link" size="small">
              {item.actionLabel}
            </Button>
          </Link>
        </div>
      ))}
    </div>
  );
}

export function DatabaseManagementPage() {
  const { message } = AntApp.useApp();
  const pageRef = useRef<HTMLDivElement>(null);
  const search = useSearch({ from: '/data-system/database' });
  const navigate = useNavigate({ from: '/data-system/database' });
  const hasLineageFilters = Boolean(
    search.lineageBatchId ||
      search.lineageDatasetName ||
      search.lineageSymbol ||
      search.lineageTradeDate ||
      search.lineageSource ||
      search.lineageStatus,
  );
  const hasQualityFilters = Boolean(
    search.qualityDatasetName || search.qualityStatus || search.qualitySeverity || search.qualityCheckedAt,
  );
  const shouldOpenCalendar = search.view === 'calendar';
  const shouldOpenQuality = search.view === 'quality' || hasQualityFilters;
  const [lineageEnabled, setLineageEnabled] = useState(hasLineageFilters);
  const [calendarEnabled, setCalendarEnabled] = useState(shouldOpenCalendar);
  const [qualityEnabled, setQualityEnabled] = useState(shouldOpenQuality);
  const selectedMarket = search.market || DEFAULT_MARKET;
  useEffect(() => {
    if (hasLineageFilters) {
      setLineageEnabled(true);
    }
  }, [hasLineageFilters]);
  useEffect(() => {
    if (shouldOpenCalendar) {
      setCalendarEnabled(true);
      window.requestAnimationFrame(() => document.querySelector('#database-calendar-section')?.scrollIntoView({ block: 'start' }));
    }
  }, [shouldOpenCalendar]);
  useEffect(() => {
    if (shouldOpenQuality) {
      setQualityEnabled(true);
      window.requestAnimationFrame(() => document.querySelector('#database-quality-section')?.scrollIntoView({ block: 'start' }));
    }
  }, [shouldOpenQuality]);
  const qualityParams = useMemo<DataQualityReportListParams>(
    () => ({
      datasetName: search.qualityDatasetName ?? '',
      status: search.qualityStatus ?? '',
      severity: search.qualitySeverity ?? '',
      checkedAt: search.qualityCheckedAt ?? '',
      page: search.qualityPage ?? FIRST_PAGE,
      pageSize: search.qualityPageSize ?? REPORT_PAGE_SIZE,
    }),
    [
      search.qualityCheckedAt,
      search.qualityDatasetName,
      search.qualityPage,
      search.qualityPageSize,
      search.qualitySeverity,
      search.qualityStatus,
    ],
  );
  const lineageParams = useMemo<DatabaseLineageParams>(
    () => ({
      batchId: search.lineageBatchId,
      datasetName: search.lineageDatasetName ?? '',
      market: selectedMarket,
      symbol: search.lineageSymbol ?? '',
      tradeDate: search.lineageTradeDate ?? '',
      source: search.lineageSource ?? '',
      status: search.lineageStatus ?? '',
      page: search.lineagePage ?? FIRST_PAGE,
      pageSize: search.lineagePageSize ?? LINEAGE_PAGE_SIZE,
    }),
    [
      search.lineageBatchId,
      search.lineageDatasetName,
      search.lineagePage,
      search.lineagePageSize,
      search.lineageSource,
      search.lineageStatus,
      search.lineageSymbol,
      search.lineageTradeDate,
      selectedMarket,
    ],
  );
  const datasetsQuery = useDatasetsQuery({ page: FIRST_PAGE, pageSize: DATASET_PAGE_SIZE });
  const databaseStatusQuery = useDatabaseStatusQuery();
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: selectedMarket });
  const lineageQuery = useDatabaseLineageQuery(lineageParams, { enabled: lineageEnabled });
  const calendarsQuery = useTradingCalendarsQuery({
    market: selectedMarket,
    page: FIRST_PAGE,
    pageSize: CALENDAR_PAGE_SIZE,
  }, { enabled: calendarEnabled });
  const dataSourcesQuery = useDataSourcesQuery();
  const qualityOverviewQuery = useDataQualityOverviewQuery();
  const qualityCheckRunsQuery = useDataQualityCheckRunsQuery({ enabled: qualityEnabled });
  const qualityReportsQuery = useDataQualityReportsQuery(qualityParams, { enabled: qualityEnabled });
  const qualityCheckMutation = useRunDataQualityCheckMutation();

  const datasets = datasetsQuery.data?.items ?? [];
  const calendars = calendarsQuery.data?.items ?? [];
  const dataSources = useMemo(
    () => (dataSourcesQuery.data ?? []).filter((source) => V1_DATA_SOURCE_CODES.has(source.code)),
    [dataSourcesQuery.data],
  );
  const reports = qualityReportsQuery.data?.items ?? [];
  const qualityCheckRuns = qualityCheckRunsQuery.data ?? [];
  const lineageItems = lineageQuery.data?.items ?? [];
  const databaseStatus = databaseStatusQuery.data;
  const qualityOverview = qualityOverviewQuery.data;
  const integrationOverview = integrationOverviewQuery.data;
  const coverageSummary = integrationOverview?.coverage_summary;
  const datasetSnapshots = integrationOverview?.dataset_snapshots ?? [];
  const datasetColumns = useMemo(() => buildDatasetColumns(), []);
  const snapshotColumns = useMemo(() => buildSnapshotColumns(), []);
  const watermarkColumns = useMemo(() => buildWatermarkColumns(coverageSummary), [coverageSummary]);
  const providerColumns = useMemo(() => buildProviderColumns(), []);
  const providerStatusColumns = useMemo(() => buildProviderStatusColumns(), []);
  const lineageColumns = useMemo(() => buildLineageColumns(), []);
  const storageMetricSource = useMemo(
    () => (datasetSnapshots.length > 0 ? datasetSnapshots : datasets),
    [datasetSnapshots, datasets],
  );
  const storageSummary = useMemo(() => getDatasetStorageSummary(storageMetricSource), [storageMetricSource]);
  const latestDatasetDate = getLatestDatasetDate(storageMetricSource);
  const dailyBarsSnapshot = getDatasetSnapshotByName(datasetSnapshots, 'daily_bars');
  const tradingCalendarSnapshot = getDatasetSnapshotByName(datasetSnapshots, 'trading_calendars');
  const latestCalendarDate = calendars[0]?.trade_date;
  const calendarCoverageStats = useMemo(
    () => getCalendarCoverageStats(calendars, coverageSummary, tradingCalendarSnapshot),
    [calendars, coverageSummary, tradingCalendarSnapshot],
  );
  const totalRows = getDatasetRowsTotal(storageMetricSource);
  const integrationSummary = integrationOverview?.summary;
  const datasetsTotal = integrationSummary?.datasets_total ?? datasetsQuery.data?.total ?? 0;
  const rowsTotal = integrationSummary?.total_rows ?? totalRows;
  const qualityRunOptions = useMemo(
    () => [
      { label: '最新检查批次', value: '' },
      ...qualityCheckRuns.map((run) => ({
        label: `${formatDateTime(run.checked_at)} / ${formatNumber(run.reports_total)} 条`,
        value: run.checked_at,
      })),
    ],
    [qualityCheckRuns],
  );

  const traceRecentBatch = useCallback(
    (batch: RecentIngestBatch) => {
      void navigate({
        search: {
          ...search,
          lineageBatchId: Number(batch.id),
          lineageDatasetName: batch.dataset_name,
          lineageSymbol: batch.symbol ?? undefined,
          lineageTradeDate: batch.end_date ?? batch.start_date ?? undefined,
          lineageSource: batch.source,
          lineageStatus: batch.status,
          lineagePage: FIRST_PAGE,
          lineagePageSize: lineageParams.pageSize,
        },
      });
      scrollToLineageSection();
    },
    [lineageParams.pageSize, navigate, search],
  );

  const traceQualityReportBatch = useCallback(
    (report: DataQualityReport) => {
      const trace = report.trace;
      const batchId = getNumericRecordId(trace?.latest_batch_id);
      if (!trace || !batchId) {
        return;
      }

      void navigate({
        search: {
          ...search,
          market: trace.latest_batch_market || search.market || selectedMarket,
          lineageBatchId: batchId,
          lineageDatasetName: report.dataset_name,
          lineageSymbol: trace.latest_batch_symbol ?? undefined,
          lineageTradeDate: trace.latest_batch_end_date ?? trace.latest_batch_start_date ?? undefined,
          lineageSource: trace.latest_batch_source || trace.dataset_source || undefined,
          lineageStatus: trace.latest_batch_status || undefined,
          lineagePage: FIRST_PAGE,
          lineagePageSize: lineageParams.pageSize,
        },
      });
      scrollToLineageSection();
    },
    [lineageParams.pageSize, navigate, search, selectedMarket],
  );

  const reportColumns = useMemo(
    () => buildReportColumns(coverageSummary, traceQualityReportBatch),
    [coverageSummary, traceQualityReportBatch],
  );
  const batchColumns = useMemo(() => buildBatchColumns(traceRecentBatch), [traceRecentBatch]);

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.05, y: 8 });
      fadeInUp(root.querySelectorAll('.database-panel'), { delay: 0.08, stagger: 0.04, y: 10 });
    },
    { scope: pageRef },
  );

  const refreshAll = () => {
    void datasetsQuery.refetch();
    void databaseStatusQuery.refetch();
    void integrationOverviewQuery.refetch();
    void dataSourcesQuery.refetch();
    void qualityOverviewQuery.refetch();
    if (lineageEnabled) {
      void lineageQuery.refetch();
    }
    if (calendarEnabled) {
      void calendarsQuery.refetch();
    }
    if (qualityEnabled) {
      void qualityCheckRunsQuery.refetch();
      void qualityReportsQuery.refetch();
    }
  };

  const runQualityCheck = () => {
    qualityCheckMutation.mutate(undefined, {
      onSuccess: (result) => {
        void message.success(`已检查 ${result.checked_datasets} 个数据集，生成 ${result.reports_created} 条质量报告`);
        void qualityOverviewQuery.refetch();
        void qualityCheckRunsQuery.refetch();
        void qualityReportsQuery.refetch();
        void integrationOverviewQuery.refetch();
        void datasetsQuery.refetch();
      },
      onError: (error) => {
        void message.error(error instanceof Error ? error.message : '数据质量检查执行失败');
      },
    });
  };

  return (
    <div className="workbench database-page" ref={pageRef}>
      <div className="workbench-heading database-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>数据库管理</Typography.Title>
          <Typography.Text type="secondary">
            查看股票池、日线行情、交易日历、同步批次和数据质量的存储状态与整合状态
          </Typography.Text>
        </Space>
        <Space wrap className="database-heading-actions">
          <Select
            className="database-market-select"
            value={selectedMarket}
            options={databaseMarketOptions}
            onChange={(market) => {
              void navigate({
                search: {
                  ...search,
                  market,
                  qualityPage: FIRST_PAGE,
                  lineagePage: FIRST_PAGE,
                },
              });
            }}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={refreshAll}
            loading={
              datasetsQuery.isFetching ||
              databaseStatusQuery.isFetching ||
              integrationOverviewQuery.isFetching ||
              dataSourcesQuery.isFetching ||
              lineageQuery.isFetching ||
              calendarsQuery.isFetching ||
              qualityOverviewQuery.isFetching ||
              qualityReportsQuery.isFetching
            }
          >
            刷新状态
          </Button>
        </Space>
      </div>

      <DataClosedLoopPanel
        overview={integrationOverview}
        loading={integrationOverviewQuery.isLoading}
        error={integrationOverviewQuery.isError}
      />

      <Row gutter={[16, 16]} className="summary-row database-status-row">
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="当前元数据库"
              value={getMetadataStoreLabel(databaseStatus?.database_kind)}
              prefix={<DatabaseOutlined />}
              loading={databaseStatusQuery.isLoading}
            />
            <Typography.Text type="secondary">
              {formatDatabaseRole(databaseStatus?.database_role)} / 本地文件容量 {formatBytes(databaseStatus?.database_size_bytes)}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="行情数据湖"
              value={formatBytes(databaseStatus?.data_lake_size_bytes)}
              prefix={<FileSearchOutlined />}
              loading={databaseStatusQuery.isLoading}
            />
            <Typography.Text type="secondary">
              Parquet {formatNumber(databaseStatus?.parquet_file_count ?? 0)} / 文件{' '}
              {formatNumber(databaseStatus?.total_file_count ?? 0)}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="日线最新数据日"
              value={formatDate(dailyBarsSnapshot?.latest_data_date ?? integrationSummary?.latest_data_date ?? latestDatasetDate)}
              prefix={<CalendarOutlined />}
              loading={datasetsQuery.isLoading || integrationOverviewQuery.isLoading}
            />
            <Typography.Text type="secondary">
              交易日历到 {latestCalendarDate ? formatDate(latestCalendarDate) : '-'}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="质量错误"
              value={qualityOverview?.reports_error ?? 0}
              suffix="条"
              prefix={<SafetyCertificateOutlined />}
              loading={qualityOverviewQuery.isLoading}
            />
            <Typography.Text type="secondary">
              通过 {formatNumber(qualityOverview?.datasets_good ?? 0)} / 总计{' '}
              {formatNumber(qualityOverview?.datasets_total ?? 0)}
            </Typography.Text>
          </Card>
        </Col>
      </Row>

      <div className="database-section-nav">
        <a href="#database-coverage-section">覆盖</a>
        <a href="#database-storage-section">存储</a>
        <a href="#database-providers-section">数据源</a>
        <a href="#database-freshness-section">新鲜度</a>
        <a href="#database-lineage-section">批次追溯</a>
        <a href="#database-datasets-section">目录</a>
        <a href="#database-quality-section">质量</a>
      </div>

      <Row id="database-storage-section" gutter={[16, 16]} className="database-storage-row">
        <Col xs={24} xl={12}>
          <Card className="database-panel database-storage-card" title="存储位置">
            {databaseStatusQuery.isError ? (
              <Alert type="error" showIcon message="数据库状态加载失败" />
            ) : databaseStatusQuery.isLoading ? (
              <Skeleton active paragraph={{ rows: 3 }} />
            ) : (
              <Space direction="vertical" size={8}>
                <Alert
                  type={databaseStatus?.database_role === 'local_fallback' ? 'info' : 'success'}
                  showIcon
                  message={databaseStatus?.database_note}
                />
                <div className="database-storage-map">
                  <div>
                    <Typography.Text strong>元数据库</Typography.Text>
                    <Typography.Text type="secondary">股票池、数据源、同步任务、批次、目录和质量报告</Typography.Text>
                    <Typography.Text code>{databaseStatus?.database_url}</Typography.Text>
                  </div>
                  <div>
                    <Typography.Text strong>行情数据湖</Typography.Text>
                    <Typography.Text type="secondary">日线等大规模行情数据，以 Parquet 文件保存</Typography.Text>
                    <Typography.Text code>{databaseStatus?.data_lake_path}</Typography.Text>
                  </div>
                  <div>
                    <Typography.Text strong>查询引擎</Typography.Text>
                    <Typography.Text type="secondary">DuckDB 负责扫描和聚合 Parquet，不作为主存储库</Typography.Text>
                    <Space size={[6, 6]} wrap>
                      <Typography.Text code>DuckDB / Parquet Reader</Typography.Text>
                      <Tag color={getDuckDbEngineStatusColor(databaseStatus?.duckdb_engine_status)}>
                        {formatDuckDbEngineStatus(databaseStatus?.duckdb_engine_status)}
                      </Tag>
                    </Space>
                    <Typography.Text type="secondary">{databaseStatus?.duckdb_engine_note}</Typography.Text>
                  </div>
                </div>
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="database-panel database-storage-card" title="数据内容概览">
            <div className="database-storage-summary-grid">
              <div>
                <Typography.Text type="secondary">数据集</Typography.Text>
                <Typography.Title level={4}>{formatNumber(datasetsTotal)} 个</Typography.Title>
              </div>
              <div>
                <Typography.Text type="secondary">元数据表</Typography.Text>
                <Typography.Title level={4}>{formatNumber(storageSummary.postgres ?? 0)} 个</Typography.Title>
                <Tag>PostgreSQL 元数据 / SQLite 本地备用</Tag>
              </div>
              <div>
                <Typography.Text type="secondary">行情文件集</Typography.Text>
                <Typography.Title level={4}>{formatNumber(storageSummary.parquet ?? 0)} 个</Typography.Title>
                <Tag color="blue">Parquet 数据湖</Tag>
              </div>
              <div>
                <Typography.Text type="secondary">查询方式</Typography.Text>
                <Typography.Title level={4}>DuckDB</Typography.Title>
                <Tag color="green">查询引擎，不是主库</Tag>
              </div>
            </div>
            <Typography.Text type="secondary">全量目录记录 {formatNumber(rowsTotal)} 行；正式业务通过 API 读取，不直接暴露文件路径。</Typography.Text>
          </Card>
        </Col>
      </Row>

      <Card id="database-coverage-section" className="database-panel database-coverage-card" title="覆盖率摘要">
        <CoverageSummaryPanel
          coverage={integrationOverview?.coverage_summary}
          loading={integrationOverviewQuery.isLoading}
          error={integrationOverviewQuery.isError}
        />
      </Card>

      <Card id="database-freshness-section" className="database-panel database-freshness-card" title="数据新鲜度">
        <DataFreshnessPanel
          snapshots={datasetSnapshots}
          loading={integrationOverviewQuery.isLoading}
          error={integrationOverviewQuery.isError}
        />
      </Card>

      <Card id="database-lineage-section" className="database-panel database-table-card" title="批次级数据血缘查询">
        <Space className="database-lineage-stack" direction="vertical" size={14}>
          <Alert
            type="info"
            showIcon
            message="按入库批次追溯数据从哪里来、写到了哪里"
            description="这里查询的是 V1 批次级血缘：请求来源、实际来源、任务、schema/normalize 版本、记录数、质量和失败原因；暂不做字段级血缘和复杂 DAG。"
          />
          <Form<LineageFilterValues>
            key={[
              lineageParams.batchId ?? '',
              lineageParams.datasetName,
              lineageParams.symbol,
              lineageParams.tradeDate,
              lineageParams.source,
              lineageParams.status,
            ].join('|')}
            className="stock-filters database-lineage-filters"
            layout="inline"
            initialValues={{
              batchId: lineageParams.batchId,
              datasetName: lineageParams.datasetName,
              symbol: lineageParams.symbol,
              tradeDate: lineageParams.tradeDate ? dayjs(lineageParams.tradeDate) : undefined,
              source: lineageParams.source,
              status: lineageParams.status,
            }}
            onFinish={(values) => {
              setLineageEnabled(true);
              void navigate({
                search: {
                  ...search,
                  lineageBatchId: values.batchId || undefined,
                  lineageDatasetName: values.datasetName || undefined,
                  lineageSymbol: values.symbol?.trim() || undefined,
                  lineageTradeDate: values.tradeDate?.format('YYYY-MM-DD'),
                  lineageSource: values.source?.trim() || undefined,
                  lineageStatus: values.status || undefined,
                  lineagePage: FIRST_PAGE,
                  lineagePageSize: lineageParams.pageSize,
                },
              });
            }}
          >
            <Form.Item label="批次 ID" name="batchId" className="filter-keyword">
              <InputNumber className="full-width-control" min={1} precision={0} placeholder="如 23" />
            </Form.Item>
            <Form.Item label="数据集" name="datasetName">
              <Select className="filter-select-wide" options={lineageDatasetOptions} />
            </Form.Item>
            <Form.Item label="股票代码" name="symbol" className="filter-keyword">
              <Input allowClear placeholder="如 600519" />
            </Form.Item>
            <Form.Item label="交易日" name="tradeDate">
              <DatePicker className="full-width-control" />
            </Form.Item>
            <Form.Item label="来源" name="source" className="filter-keyword">
              <Input allowClear placeholder="如 akshare / adata / stock_sdk" />
            </Form.Item>
            <Form.Item label="状态" name="status">
              <Select className="filter-select" options={lineageStatusOptions} />
            </Form.Item>
            <Form.Item className="filter-actions">
              <Space wrap>
                <Button type="primary" htmlType="submit">
                  查询血缘
                </Button>
                <Button
                  onClick={() => {
                    setLineageEnabled(true);
                    void navigate({
                      search: {
                        ...search,
                        lineageBatchId: undefined,
                        lineageDatasetName: undefined,
                        lineageSymbol: undefined,
                        lineageTradeDate: undefined,
                        lineageSource: undefined,
                        lineageStatus: undefined,
                        lineagePage: FIRST_PAGE,
                        lineagePageSize: lineageParams.pageSize,
                      },
                    });
                  }}
                >
                  重置
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  loading={lineageQuery.isFetching}
                  onClick={() => {
                    if (!lineageEnabled) {
                      setLineageEnabled(true);
                      return;
                    }
                    void lineageQuery.refetch();
                  }}
                >
                  刷新
                </Button>
              </Space>
            </Form.Item>
          </Form>
          {lineageEnabled ? (
            lineageQuery.isError ? (
              <Alert type="error" showIcon message="批次血缘加载失败" description="后端批次血缘接口暂不可用。" />
            ) : (
              <Table<DatabaseLineageItem>
                rowKey={(record) => String(record.id)}
                columns={lineageColumns}
                dataSource={lineageItems}
                loading={lineageQuery.isFetching}
                size="small"
                scroll={{ x: 1420 }}
                locale={{
                  emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无批次级血缘记录" />,
                }}
                pagination={{
                  current: lineageParams.page,
                  pageSize: lineageParams.pageSize,
                  total: lineageQuery.data?.total ?? 0,
                  showSizeChanger: false,
                  showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${formatNumber(total)} 条`,
                  onChange: (page, pageSize) => {
                    void navigate({
                      search: {
                        ...search,
                        lineageBatchId: lineageParams.batchId || undefined,
                        lineageDatasetName: lineageParams.datasetName || undefined,
                        lineageSymbol: lineageParams.symbol || undefined,
                        lineageTradeDate: lineageParams.tradeDate || undefined,
                        lineageSource: lineageParams.source || undefined,
                        lineageStatus: lineageParams.status || undefined,
                        lineagePage: page,
                        lineagePageSize: pageSize,
                      },
                    });
                  },
                }}
              />
            )
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="默认不加载批次血缘。使用筛选或点击“刷新”后再查看。"
            />
          )}
        </Space>
      </Card>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={14}>
          <Card className="database-panel database-table-card" title="数据版本 / 快照">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="数据整合总览加载失败" description="后端整合总览接口暂不可用。" />
            ) : (
              <Table<DatasetSnapshot>
                rowKey={(record) => record.dataset_name}
                columns={snapshotColumns}
                dataSource={datasetSnapshots}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                scroll={{ x: 980 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据集快照" /> }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="database-panel database-table-card" title="同步水位线">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="同步水位线加载失败" />
            ) : (
              <Table<SyncWatermark>
                rowKey={(record) => `${record.dataset_name}-${record.source}-${record.market}-${record.symbol}-${record.batch_id}`}
                columns={watermarkColumns}
                dataSource={integrationOverview?.sync_watermarks ?? []}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 1320 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无成功水位线" /> }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={11}>
          <Card id="database-providers-section" className="database-panel database-table-card" title="Provider 状态与取样">
            {dataSourcesQuery.isError ? (
              <Alert type="error" showIcon message="数据源状态加载失败" description="后端数据源管理接口暂不可用。" />
            ) : (
              <Table<DataSource>
                rowKey={(record) => record.code}
                columns={providerStatusColumns}
                dataSource={dataSources}
                loading={dataSourcesQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 980 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据源状态" /> }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={13}>
          <Card className="database-panel database-table-card" title="数据源整合概况">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="数据源整合概况加载失败" />
            ) : (
              <Table<ProviderIntegration>
                rowKey={(record) => record.source}
                columns={providerColumns}
                dataSource={integrationOverview?.provider_integrations ?? []}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 850 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据源批次" /> }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col span={24}>
          <Card className="database-panel database-table-card" title="最近入库批次（worker 执行结果）">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="最近批次加载失败" />
            ) : (
              <Table<RecentIngestBatch>
                rowKey={(record) => String(record.id)}
                columns={batchColumns}
                dataSource={integrationOverview?.recent_batches ?? []}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 1080 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无整合批次" /> }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={16}>
          <Card id="database-datasets-section" className="database-panel database-table-card" title="存放内容">
            {datasetsQuery.isError ? (
              <Alert type="error" showIcon message="数据集加载失败" description="后端数据集接口暂不可用。" />
            ) : (
              <Table<Dataset>
                rowKey={(record) => String(record.id)}
                columns={datasetColumns}
                dataSource={datasets}
                loading={datasetsQuery.isFetching}
                pagination={false}
                scroll={{ x: 1100 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据集" /> }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card id="database-calendar-section" className="database-panel database-calendar-card" title="交易日历覆盖">
            <Space direction="vertical" size={12}>
              <Space wrap>
                <Button
                  type="primary"
                  icon={<CalendarOutlined />}
                  onClick={() => {
                    setCalendarEnabled(true);
                  }}
                >
                  加载交易日历
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  loading={calendarsQuery.isFetching}
                  onClick={() => {
                    if (!calendarEnabled) {
                      setCalendarEnabled(true);
                      return;
                    }
                    void calendarsQuery.refetch();
                  }}
                >
                  刷新
                </Button>
              </Space>
              {calendarEnabled ? (
                calendarsQuery.isError ? (
                  <Alert type="error" showIcon message="交易日历加载失败" />
                ) : calendarsQuery.isLoading || integrationOverviewQuery.isLoading ? (
                  <Skeleton active paragraph={{ rows: 6 }} />
                ) : calendars.length === 0 && !calendarCoverageStats.latestDate ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无交易日历" />
                ) : (
                  <Space className="database-calendar-stack" direction="vertical" size={12}>
                    <div className="database-calendar-summary-grid">
                      <div>
                        <Typography.Text type="secondary">覆盖范围</Typography.Text>
                        <Typography.Title level={5}>
                          {formatRange(calendarCoverageStats.coverageStart, calendarCoverageStats.coverageEnd)}
                        </Typography.Title>
                      </div>
                      <div>
                        <Typography.Text type="secondary">最新日历日期</Typography.Text>
                        <Typography.Title level={5}>{formatDate(calendarCoverageStats.latestDate)}</Typography.Title>
                      </div>
                      <div>
                        <Typography.Text type="secondary">当前样本</Typography.Text>
                        <Typography.Title level={5}>{formatNumber(calendarCoverageStats.loadedTotal)} 天</Typography.Title>
                        <Typography.Text type="secondary">
                          {formatRange(calendarCoverageStats.loadedStart, calendarCoverageStats.loadedEnd)}
                        </Typography.Text>
                      </div>
                      <div>
                        <Typography.Text type="secondary">开市 / 休市</Typography.Text>
                        <Typography.Title level={5}>
                          {formatNumber(calendarCoverageStats.loadedOpenDays)} / {formatNumber(calendarCoverageStats.loadedClosedDays)}
                        </Typography.Title>
                        <Typography.Text type="secondary">按当前已加载样本</Typography.Text>
                      </div>
                    </div>
                    <List
                      className="database-calendar-list"
                      dataSource={calendars}
                      renderItem={(day) => (
                        <List.Item>
                          <Space className="database-calendar-row">
                            <Typography.Text strong>{formatDate(day.trade_date)}</Typography.Text>
                            <Tag color={day.is_open ? 'green' : 'default'}>{day.is_open ? '开市' : '休市'}</Tag>
                            <Typography.Text type="secondary">{formatMarket(day.market)}</Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Space>
                )
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="默认不加载交易日历样本。点击“加载交易日历”后再查看。"
                />
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      <Card id="database-quality-section" className="database-panel database-quality-card" title="质量风险">
        {qualityOverviewQuery.isError ? (
          <Alert type="error" showIcon message="质量信息加载失败" />
        ) : (
          <Space className="database-quality-stack" direction="vertical" size={14}>
            <div className="database-quality-toolbar">
              <Form
                className="stock-filters quality-filters database-quality-filters"
                layout="inline"
                initialValues={{
                  checkedAt: qualityParams.checkedAt,
                  datasetName: qualityParams.datasetName,
                  status: qualityParams.status,
                  severity: qualityParams.severity,
                }}
                onFinish={(values: { checkedAt?: string; datasetName?: string; status?: string; severity?: string }) => {
                  setQualityEnabled(true);
                  void navigate({
                    search: {
                      ...search,
                      qualityCheckedAt: values.checkedAt || undefined,
                      qualityDatasetName: values.datasetName?.trim() || undefined,
                      qualityStatus: values.status || undefined,
                      qualitySeverity: values.severity || undefined,
                      qualityPage: FIRST_PAGE,
                      qualityPageSize: qualityParams.pageSize,
                    },
                  });
                }}
              >
                <Form.Item name="checkedAt">
                  <Select className="filter-select-wide" options={qualityRunOptions} loading={qualityCheckRunsQuery.isFetching} />
                </Form.Item>
                <Form.Item name="datasetName" className="filter-keyword">
                  <Input allowClear placeholder="数据集名称，如 daily_bars" />
                </Form.Item>
                <Form.Item name="status">
                  <Select className="filter-select" options={qualityStatusOptions} />
                </Form.Item>
                <Form.Item name="severity">
                  <Select className="filter-select-wide" options={qualitySeverityOptions} />
                </Form.Item>
                <Form.Item className="filter-actions">
                  <Space wrap>
                    <Button
                      type="primary"
                      htmlType="submit"
                      onClick={() => {
                        setQualityEnabled(true);
                      }}
                    >
                      查询
                    </Button>
                    <Button
                      icon={<ReloadOutlined />}
                      loading={qualityOverviewQuery.isFetching || qualityCheckRunsQuery.isFetching || qualityReportsQuery.isFetching}
                      onClick={() => {
                        void qualityOverviewQuery.refetch();
                        if (!qualityEnabled) {
                          setQualityEnabled(true);
                          return;
                        }
                        void qualityCheckRunsQuery.refetch();
                        void qualityReportsQuery.refetch();
                      }}
                    >
                      刷新
                    </Button>
                    <Button
                      type="primary"
                      icon={<SafetyCertificateOutlined />}
                      loading={qualityCheckMutation.isPending}
                      onClick={() => {
                        setQualityEnabled(true);
                        runQualityCheck();
                      }}
                    >
                      运行检查
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
              <Typography.Text type="secondary">
                当前批次：{formatDateTime(qualityReportsQuery.data?.checked_at ?? qualityParams.checkedAt)}；历史报告总数 {formatNumber(qualityOverview?.reports_total ?? 0)}
              </Typography.Text>
            </div>
            {qualityEnabled ? (
              qualityReportsQuery.isLoading ? (
                <Skeleton active paragraph={{ rows: 4 }} />
              ) : (
                <Table<DataQualityReport>
                  rowKey={(record) => String(record.id)}
                  columns={reportColumns}
                  dataSource={reports}
                  loading={qualityReportsQuery.isFetching || qualityCheckMutation.isPending}
                  pagination={{
                    current: qualityParams.page,
                    pageSize: qualityParams.pageSize,
                    total: qualityReportsQuery.data?.total ?? 0,
                    showSizeChanger: false,
                    showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${formatNumber(total)} 条`,
                    onChange: (page, pageSize) => {
                      void navigate({
                        search: {
                          ...search,
                          qualityDatasetName: qualityParams.datasetName || undefined,
                          qualityCheckedAt: qualityParams.checkedAt || undefined,
                          qualityStatus: qualityParams.status || undefined,
                          qualitySeverity: qualityParams.severity || undefined,
                          qualityPage: page,
                          qualityPageSize: pageSize,
                        },
                      });
                    },
                  }}
                  scroll={{ x: 1440 }}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无质量报告" /> }}
                />
              )
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="默认不加载质量明细。先点击“查询”或“运行检查”再展开报告。"
              />
            )}
          </Space>
        )}
      </Card>
    </div>
  );
}
