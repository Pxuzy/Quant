import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { CalendarOutlined, FileTextOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
} from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import type { DataSource } from '../../../features/data-sources/types';
import { useDatabaseIntegrationOverviewQuery } from '../../../features/database/api';
import type {
  DatabaseCoverageSummary,
  DatabaseIntegrationOverview,
  RecentIngestBatch,
  SyncWatermark,
} from '../../../features/database/types';
import {
  usePreviewDailyBarsMarketRepairMutation,
  useSyncDailyBarsMarketRepairMutation,
  useSyncDailyBarsMutation,
} from '../../../features/market-data/api';
import type { DailyBarsMarketRepairPreviewResponse } from '../../../features/market-data/types';
import { useSyncStocksMutation } from '../../../features/stocks/api';
import {
  useSyncTaskLogsQuery,
  useSyncTaskIngestBatchesQuery,
  useSyncTaskQuery,
  useSyncTasksQuery,
  useSyncRunnerStatusQuery,
  useSyncSchedulesQuery,
  useTriggerSyncScheduleMutation,
  useUpdateSyncScheduleMutation,
} from '../../../features/sync-tasks/api';
import type {
  IngestBatch,
  SyncRunnerStatus,
  SyncRunnerTaskRef,
  SyncSchedule,
  SyncTask,
  SyncTaskLog,
  SyncTaskListParams,
} from '../../../features/sync-tasks/types';
import { useSyncTradingCalendarsMutation } from '../../../features/trading-calendars/api';
import { ErrorState } from '../../../shared/components/ErrorState';
import { formatDate, formatDateTime, formatNumber } from '../../../shared/components/formatters';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatAdjustType, formatLogLevel, formatMarket, formatSourceMode, formatTaskType } from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';
import { SyncConsolePanel as SyncConsolePanelCard } from './components/SyncConsolePanel';
import { SyncOperationTabs as SyncOperationTabsCard } from './components/SyncOperationTabs';
import { TaskDetailDrawer as SyncTaskDetailDrawer } from './components/TaskDetailDrawer';

const DEFAULT_PAGE_SIZE = 10;
const DEFAULT_MARKET = 'A_SHARE';
const SYMBOL_EXAMPLE = '600519';
const DEFAULT_DATE_RANGE: [Dayjs, Dayjs] = [dayjs().subtract(90, 'day'), dayjs()];
const DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20;
const MAX_MARKET_REPAIR_SYMBOLS = 200;
const DEFAULT_MARKET_REPAIR_START_POLICY = 'requested_start';
const DEFAULT_ADJUST_TYPE: 'none' | 'qfq' | 'hfq' = 'none';
const adjustTypeOptions = [
  { label: '不复权', value: 'none' },
  { label: '前复权', value: 'qfq' },
  { label: '后复权', value: 'hfq' },
];
const syncFocusLabels: Record<string, string> = {
  'stock-list': '手动同步股票池',
  'daily-bars': '手动同步日线',
  'daily-bars-market-repair': '市场级日线缺口补齐',
  calendars: '交易日历同步',
};

type DailyBarsMode = 'single' | 'market-repair';
type SyncOperationTab = 'daily-bars' | 'stock-list' | 'calendars';

type MarketRepairFormValues = {
  source?: string;
  market?: string;
  dateRange?: [Dayjs, Dayjs];
  maxSymbols?: number;
  startPolicy?: 'requested_start' | 'listing_date';
  adjustType?: 'none' | 'qfq' | 'hfq';
};

type TaskCreatedSearch = Pick<
  SyncTaskListParams,
  'status' | 'source' | 'taskType' | 'market' | 'symbol' | 'startDate' | 'endDate' | 'page' | 'pageSize'
> & {
  focus?: string;
  taskId?: number;
};

type ScheduleFormValues = {
  source?: string;
  market?: string;
  symbol?: string;
  cron_expression?: string;
};

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '等待中', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
];

const taskTypeOptions = [
  { label: '全部类型', value: '' },
  { label: formatTaskType('stock_list'), value: 'stock_list' },
  { label: formatTaskType('daily_bars'), value: 'daily_bars' },
  { label: formatTaskType('daily_bars_market_repair'), value: 'daily_bars_market_repair' },
  { label: formatTaskType('calendars'), value: 'calendars' },
];

function getTaskType(task?: SyncTask | null) {
  const type = task?.task_type ?? task?.taskType ?? '-';
  return formatTaskType(type);
}
function normalizeMarketRepairMaxSymbols(value?: number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_MARKET_REPAIR_MAX_SYMBOLS;
  }
  return Math.min(MAX_MARKET_REPAIR_SYMBOLS, Math.max(1, Math.trunc(numeric)));
}

function getRecordsRead(task?: SyncTask | null) {
  return task?.records_read ?? task?.recordsRead ?? 0;
}

function getRecordsWritten(task?: SyncTask | null) {
  return task?.records_written ?? task?.recordsWritten ?? 0;
}

function getErrorMessage(task?: SyncTask | null) {
  return task?.error_message ?? task?.errorMessage;
}

function getCreatedAt(task?: SyncTask | null) {
  return task?.created_at ?? task?.createdAt;
}

function getStartedAt(task?: SyncTask | null) {
  return task?.started_at ?? task?.startedAt;
}

function getFinishedAt(task?: SyncTask | null) {
  return task?.finished_at ?? task?.finishedAt;
}

function getTaskCandidateSources(task?: SyncTask | null) {
  const sources = task?.candidate_sources ?? task?.candidateSources ?? [];
  return Array.isArray(sources) ? sources.filter((source): source is string => Boolean(source?.trim())) : [];
}

function getTaskSelectedSource(task?: SyncTask | null) {
  const source = task?.selected_source ?? task?.selectedSource;
  return source?.trim() || null;
}

function getDataSourceCapabilities(source: DataSource) {
  return source.capabilities ?? source.config_json?.capabilities ?? {};
}

function getLogPayload(log: SyncTaskLog) {
  return log.payload_json ?? log.payloadJson;
}

function getLogTime(log: SyncTaskLog) {
  return log.created_at ?? log.createdAt;
}

function getBatchDataset(batch: IngestBatch) {
  return batch.dataset_name ?? batch.datasetName ?? '-';
}

function getBatchRequestedSource(batch: IngestBatch) {
  return batch.requested_source ?? batch.requestedSource;
}

function getBatchMarket(batch: IngestBatch) {
  return batch.market;
}

function getBatchSymbol(batch: IngestBatch) {
  return batch.symbol;
}

function getBatchStartDate(batch: IngestBatch) {
  return batch.start_date ?? batch.startDate;
}

function getBatchEndDate(batch: IngestBatch) {
  return batch.end_date ?? batch.endDate;
}

function getBatchSchemaVersion(batch: IngestBatch) {
  return batch.schema_version ?? batch.schemaVersion ?? '-';
}

function getBatchNormalizeVersion(batch: IngestBatch) {
  return batch.normalize_version ?? batch.normalizeVersion ?? '-';
}

function getBatchRawRecords(batch: IngestBatch) {
  return batch.raw_records ?? batch.rawRecords ?? 0;
}

function getBatchNormalizedRecords(batch: IngestBatch) {
  return batch.normalized_records ?? batch.normalizedRecords ?? 0;
}

function getBatchRecordsWritten(batch: IngestBatch) {
  return batch.records_written ?? batch.recordsWritten ?? 0;
}

function getBatchValidationErrors(batch: IngestBatch) {
  return batch.validation_errors_json ?? batch.validationErrorsJson ?? [];
}

function getBatchErrorMessage(batch: IngestBatch) {
  return batch.error_message ?? batch.errorMessage;
}

function getBatchQualityStatus(batch: IngestBatch) {
  return batch.quality_status ?? batch.qualityStatus ?? '-';
}

function getBatchStartedAt(batch: IngestBatch) {
  return batch.started_at ?? batch.startedAt;
}

function getBatchFinishedAt(batch: IngestBatch) {
  return batch.finished_at ?? batch.finishedAt;
}

function formatTaskSource(value?: string | null) {
  return value === 'auto' ? formatSourceMode(value) : value || '-';
}

function renderTaskSourceEvidence(task?: SyncTask | null) {
  const requestedSource = task?.source;
  const selectedSource = getTaskSelectedSource(task);
  const candidateSources = getTaskCandidateSources(task);
  const isAutoSource = !requestedSource || requestedSource === 'auto';
  const primaryText = selectedSource ?? (isAutoSource ? '-' : requestedSource);
  const candidateText = candidateSources.join(' / ');

  return (
    <Space direction="vertical" size={0}>
      <Typography.Text>{primaryText}</Typography.Text>
      <Typography.Text type="secondary" ellipsis title={candidateText || undefined}>
        {selectedSource
          ? candidateText || '自动选择已确认'
          : isAutoSource
            ? candidateText
              ? `候选 ${candidateText}`
              : '等待任务日志'
            : '手动指定'}
      </Typography.Text>
    </Space>
  );
}

function formatWatermarkScope(watermark: SyncWatermark) {
  const market = formatMarket(watermark.market);
  return watermark.symbol ? `${market} / ${watermark.symbol}` : market;
}

function formatWatermarkRepairRange(watermark: SyncWatermark) {
  if (!watermark.repair_start_date && !watermark.repair_end_date) {
    return '-';
  }
  if (watermark.repair_start_date && watermark.repair_end_date && watermark.repair_start_date !== watermark.repair_end_date) {
    return `${formatDate(watermark.repair_start_date)} ~ ${formatDate(watermark.repair_end_date)}`;
  }
  return formatDate(watermark.repair_end_date ?? watermark.repair_start_date);
}

function isMarketDailyRepairHint(watermark: SyncWatermark) {
  return watermark.dataset_name === 'daily_bars' && watermark.repair_reason?.includes('该市场同区间日线');
}

function getWatermarkRepairFocus(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
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

function getWatermarkRepairSearch(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
  const focus = getWatermarkRepairFocus(watermark, coverage);
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

function formatBatchRange(batch: RecentIngestBatch) {
  if (!batch.start_date && !batch.end_date) {
    return '-';
  }
  if (batch.start_date && batch.end_date && batch.start_date !== batch.end_date) {
    return `${formatDate(batch.start_date)} ~ ${formatDate(batch.end_date)}`;
  }
  return formatDate(batch.end_date ?? batch.start_date);
}

function formatIngestBatchRange(batch: IngestBatch) {
  const startDate = getBatchStartDate(batch);
  const endDate = getBatchEndDate(batch);
  if (!startDate && !endDate) {
    return '-';
  }
  if (startDate && endDate && startDate !== endDate) {
    return `${formatDate(startDate)} ~ ${formatDate(endDate)}`;
  }
  return formatDate(endDate ?? startDate);
}

function canTraceBatchToStock(batch: IngestBatch) {
  return getBatchDataset(batch) === 'daily_bars' && Boolean(getBatchSymbol(batch));
}

function getNumericTaskId(value?: string | number | null) {
  const taskId = Number(value);
  return Number.isFinite(taskId) && taskId > 0 ? taskId : undefined;
}

function getRunnerTaskType(task?: SyncRunnerTaskRef) {
  return task?.task_type ?? task?.taskType;
}

function getRunnerTaskStatus(task?: SyncRunnerTaskRef) {
  return task?.status;
}

function getRunnerTaskCreatedAt(task?: SyncRunnerTaskRef) {
  return task?.created_at ?? task?.createdAt;
}

function getRunnerTaskStartedAt(task?: SyncRunnerTaskRef) {
  return task?.started_at ?? task?.startedAt;
}

function getRunnerTaskFinishedAt(task?: SyncRunnerTaskRef) {
  return task?.finished_at ?? task?.finishedAt;
}

function getRunnerTaskPrimaryTime(task?: SyncRunnerTaskRef) {
  return getRunnerTaskFinishedAt(task) ?? getRunnerTaskStartedAt(task) ?? getRunnerTaskCreatedAt(task);
}

function formatPayload(payload?: Record<string, unknown> | null) {
  if (!payload || Object.keys(payload).length === 0) {
    return '';
  }

  return JSON.stringify(payload);
}

function compactValues(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value && value !== '-'))));
}

function latestLogMessage(logs: SyncTaskLog[]) {
  const errorLog = [...logs].reverse().find((log) => log.level === 'error');
  const latestLog = logs[logs.length - 1];
  return errorLog?.message ?? latestLog?.message;
}

function summarizeTaskBatches(batches: IngestBatch[]) {
  const successCount = batches.filter((batch) => batch.status === 'success').length;
  const failedCount = batches.filter((batch) => batch.status === 'failed').length;
  const rawRecords = batches.reduce((sum, batch) => sum + getBatchRawRecords(batch), 0);
  const normalizedRecords = batches.reduce((sum, batch) => sum + getBatchNormalizedRecords(batch), 0);
  const writtenRecords = batches.reduce((sum, batch) => sum + getBatchRecordsWritten(batch), 0);
  const errorMessages = batches.map(getBatchErrorMessage).filter((message): message is string => Boolean(message));
  const startedTimes = compactValues(batches.map(getBatchStartedAt)).sort();
  const finishedTimes = compactValues(batches.map(getBatchFinishedAt)).sort();

  return {
    totalCount: batches.length,
    successCount,
    failedCount,
    rawRecords,
    normalizedRecords,
    writtenRecords,
    datasets: compactValues(batches.map(getBatchDataset)),
    sources: compactValues(batches.map((batch) => batch.source)),
    requestedSources: compactValues(batches.map(getBatchRequestedSource)),
    schemaVersions: compactValues(batches.map(getBatchSchemaVersion)),
    normalizeVersions: compactValues(batches.map(getBatchNormalizeVersion)),
    qualityStatuses: compactValues(batches.map(getBatchQualityStatus)),
    firstStartedAt: startedTimes[0],
    lastFinishedAt: finishedTimes[finishedTimes.length - 1],
    firstErrorMessage: errorMessages[0],
  };
}

function formatValueList(values: string[], fallback = '-') {
  return values.length ? values.join(' / ') : fallback;
}

function formatMarketRepairStartPolicy(value?: string | null) {
  return value === 'listing_date' ? '从上市日起' : '按填写起始日';
}

function getValidDateRangeOrDefault(startDate?: Dayjs, endDate?: Dayjs): [Dayjs, Dayjs] {
  return startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : DEFAULT_DATE_RANGE;
}

function getSyncOperationTab(focus?: string): SyncOperationTab {
  if (focus === 'stock-list') {
    return 'stock-list';
  }
  if (focus === 'calendars') {
    return 'calendars';
  }
  return 'daily-bars';
}

function buildMarketRepairPreviewColumns(): ColumnsType<NonNullable<DailyBarsMarketRepairPreviewResponse['sample_items']>[number]> {
  return [
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 92,
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary">{record.name || '-'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '交易所',
      dataIndex: 'exchange',
      width: 82,
      render: (value) => value || '-',
    },
    {
      title: '补齐范围',
      key: 'range',
      width: 160,
      render: (_, record) => `${formatDate(record.start_date)} ~ ${formatDate(record.end_date)}`,
    },
    {
      title: '缺口',
      dataIndex: 'missing_trade_days',
      width: 72,
      align: 'right',
      render: (value) => formatNumber(value),
    },
  ];
}

function MarketRepairPreviewPanel({
  preview,
  loading,
  error,
}: {
  preview?: DailyBarsMarketRepairPreviewResponse;
  loading: boolean;
  error?: unknown;
}) {
  const sampleItems = preview?.sample_items ?? [];
  const columns = useMemo(() => buildMarketRepairPreviewColumns(), []);
  const candidateSources = preview?.candidate_sources ?? [];
  const supportedExchanges = preview?.supported_exchanges ?? [];

  if (loading) {
    return (
      <div className="market-repair-preview-panel">
        <Alert type="info" showIcon message="正在生成补齐计划预览" description="系统会检查股票池、开市日和现有日线缺口。" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-repair-preview-panel">
        <Alert
          type="error"
          showIcon
          message="补齐计划预览失败"
          description={error instanceof Error ? error.message : '预览接口暂不可用，请稍后重试或直接创建任务。'}
        />
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="market-repair-preview-panel market-repair-preview-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未预览补齐计划" />
      </div>
    );
  }

  return (
    <div className="market-repair-preview-panel">
      <div className="market-repair-preview-heading">
        <Typography.Text strong>补齐计划预览</Typography.Text>
        <Space size={[6, 6]} wrap>
          <Tag color="blue">{formatMarket(preview.market, '全部市场')}</Tag>
          {preview.selected_source ? <Tag color="green">实际来源 {preview.selected_source}</Tag> : null}
        </Space>
      </div>
      {preview.message ? <Alert type="success" showIcon message={preview.message} /> : null}
      <div className="market-repair-preview-stats">
        <Statistic title="计划股票" value={preview.planned_symbols ?? 0} suffix="只" />
        <Statistic title="预计缺口" value={preview.planned_missing_symbol_days ?? 0} suffix="日" />
        <Statistic title="开市日" value={preview.open_dates_count ?? 0} suffix="天" />
        <Statistic title="安全上限" value={preview.max_symbols ?? 0} suffix="只" />
      </div>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="日期范围">
          {formatDate(preview.start_date)} ~ {formatDate(preview.end_date)}
        </Descriptions.Item>
        <Descriptions.Item label="补齐起点">{formatMarketRepairStartPolicy(preview.start_policy)}</Descriptions.Item>
        <Descriptions.Item label="股票池">{formatNumber(preview.stock_pool_count)} 只</Descriptions.Item>
        <Descriptions.Item label="预览来源">
          请求 {formatTaskSource(preview.source)} / 实际 {formatTaskSource(preview.selected_source)}
        </Descriptions.Item>
        <Descriptions.Item label="候选来源">
          {candidateSources.length ? (
            <Space size={[6, 6]} wrap>
              {candidateSources.map((source) => (
                <Tag key={source}>{source}</Tag>
              ))}
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="支持交易所">
          {supportedExchanges.length ? (
            <Space size={[6, 6]} wrap>
              {supportedExchanges.map((exchange) => (
                <Tag color="geekblue" key={exchange}>
                  {exchange}
                </Tag>
              ))}
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
      </Descriptions>
      <Table
        rowKey={(record) => `${record.symbol}-${record.exchange}-${record.start_date}-${record.end_date}`}
        columns={columns}
        dataSource={sampleItems}
        pagination={false}
        size="small"
        scroll={{ x: 420 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无样例股票" /> }}
      />
    </div>
  );
}

function TaskExecutionSummaryPanel({
  task,
  batches,
  logs,
  loading,
}: {
  task?: SyncTask;
  batches: IngestBatch[];
  logs: SyncTaskLog[];
  loading: boolean;
}) {
  const summary = summarizeTaskBatches(batches);
  const taskError = getErrorMessage(task);
  const latestMessage = latestLogMessage(logs);
  const hasBatches = summary.totalCount > 0;
  const alertType =
    task?.status === 'failed' || summary.failedCount > 0
      ? 'error'
      : task?.status === 'pending' || task?.status === 'running'
        ? 'info'
        : 'success';
  const alertMessage = hasBatches
    ? `已形成 ${formatNumber(summary.totalCount)} 个入库批次`
    : task?.status === 'pending' || task?.status === 'running'
      ? '等待 worker 创建入库批次'
      : '暂无入库批次记录';
  const alertDescription = taskError || summary.firstErrorMessage || latestMessage || '任务已创建，详情会随 worker 执行结果更新。';

  return (
    <div className="task-execution-summary">
      <div className="task-section-heading">
        <Typography.Title level={5}>执行结果摘要</Typography.Title>
        <Space size={[6, 6]} wrap>
          <StatusTag value={task?.status} />
          {summary.sources.map((source) => (
            <Tag color="blue" key={source}>
              {source}
            </Tag>
          ))}
          {summary.requestedSources.length ? (
            <Tag>请求 {formatValueList(summary.requestedSources)}</Tag>
          ) : null}
        </Space>
      </div>
      <Alert type={alertType} showIcon message={alertMessage} description={alertDescription} />
      <div className="task-execution-summary-grid" aria-busy={loading}>
        <div>
          <Typography.Text type="secondary">批次结果</Typography.Text>
          <Typography.Text strong>
            成功 {formatNumber(summary.successCount)} / 失败 {formatNumber(summary.failedCount)}
          </Typography.Text>
          <Typography.Text type="secondary">总计 {formatNumber(summary.totalCount)} 个批次</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">数据写入</Typography.Text>
          <Typography.Text strong>{formatNumber(summary.writtenRecords)} 行</Typography.Text>
          <Typography.Text type="secondary">
            原始 {formatNumber(summary.rawRecords)} / 标准化 {formatNumber(summary.normalizedRecords)}
          </Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">数据契约</Typography.Text>
          <Typography.Text strong>Schema {formatValueList(summary.schemaVersions)}</Typography.Text>
          <Typography.Text type="secondary">Normalize {formatValueList(summary.normalizeVersions)}</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">范围与质量</Typography.Text>
          <Typography.Text strong>{formatValueList(summary.datasets, getTaskType(task))}</Typography.Text>
          <Typography.Text type="secondary">质量 {formatValueList(summary.qualityStatuses)}</Typography.Text>
        </div>
        <div className="task-execution-summary-wide">
          <Typography.Text type="secondary">执行窗口</Typography.Text>
          <Typography.Text strong>
            {formatDateTime(summary.firstStartedAt || getStartedAt(task))} ~{' '}
            {formatDateTime(summary.lastFinishedAt || getFinishedAt(task))}
          </Typography.Text>
        </div>
      </div>
    </div>
  );
}

function getScheduleTaskType(schedule: SyncSchedule) {
  return schedule.task_type ?? schedule.taskType ?? '-';
}

function getScheduleCron(schedule: SyncSchedule) {
  return schedule.cron_expression ?? schedule.cronExpression ?? '-';
}

function getScheduleNote(schedule: SyncSchedule) {
  return schedule.schedule_note ?? schedule.scheduleNote ?? '';
}

function getScheduleLastTriggeredAt(schedule: SyncSchedule) {
  return schedule.last_triggered_at ?? schedule.lastTriggeredAt;
}

function getScheduleInitialValues(schedule: SyncSchedule): ScheduleFormValues {
  return {
    source: schedule.source || 'auto',
    market: schedule.market || DEFAULT_MARKET,
    symbol: schedule.symbol ?? '',
    cron_expression: getScheduleCron(schedule),
  };
}

function getScheduleScope(schedule: SyncSchedule) {
  const parts = [formatTaskType(getScheduleTaskType(schedule)), formatMarket(schedule.market), formatTaskSource(schedule.source)];
  if (schedule.symbol) {
    parts.splice(2, 0, schedule.symbol);
  }
  return parts.filter(Boolean).join(' / ');
}

function formatRunnerMode(value?: string | null) {
  if (value === 'lightweight_worker') {
    return '轻量 worker';
  }
  return value || '-';
}

function getRunnerStatusColor(status?: string) {
  if (status === 'running') {
    return 'processing';
  }
  if (status === 'pending' || status === 'warning') {
    return 'warning';
  }
  return 'success';
}

function getRunnerStatusLabel(status?: string) {
  if (status === 'running') {
    return '执行中';
  }
  if (status === 'pending') {
    return '待执行';
  }
  if (status === 'warning') {
    return '需关注';
  }
  return '空闲';
}

function getTaskStatusLabel(status?: string | null) {
  if (status === 'pending') {
    return '等待中';
  }
  if (status === 'running') {
    return '运行中';
  }
  if (status === 'success') {
    return '成功';
  }
  if (status === 'failed') {
    return '失败';
  }
  if (status === 'canceled') {
    return '已取消';
  }
  return status || '-';
}

function getScheduleCapability(schedule: SyncSchedule): 'stock_list' | 'daily_bars' | 'calendars' {
  const taskType = getScheduleTaskType(schedule);
  if (taskType === 'daily_bars' || taskType === 'daily_bars_market_repair') {
    return 'daily_bars';
  }
  if (taskType === 'calendars') {
    return 'calendars';
  }
  return 'stock_list';
}

function canTriggerSchedule(schedule: SyncSchedule) {
  return getScheduleTaskType(schedule) !== 'daily_bars' || Boolean(schedule.symbol);
}

function RunnerTaskRefItem({
  label,
  task,
  emptyText,
  onOpenTask,
}: {
  label: string;
  task?: SyncRunnerTaskRef;
  emptyText: string;
  onOpenTask: (taskId: number) => void;
}) {
  const taskId = getNumericTaskId(task?.id);
  const taskType = getRunnerTaskType(task);
  const taskStatus = getRunnerTaskStatus(task);

  return (
    <div className="sync-runner-task-ref">
      <Typography.Text type="secondary">{label}</Typography.Text>
      {taskId ? (
        <Space direction="vertical" size={4}>
          <Space size={[6, 4]} wrap>
            <Typography.Text strong>#{taskId}</Typography.Text>
            {taskStatus ? <StatusTag value={taskStatus} /> : null}
          </Space>
          <Typography.Text type="secondary">
            {taskType ? formatTaskType(taskType) : '-'} / {formatDateTime(getRunnerTaskPrimaryTime(task))}
          </Typography.Text>
          <Button type="link" size="small" icon={<FileTextOutlined />} onClick={() => onOpenTask(taskId)}>
            打开任务
          </Button>
        </Space>
      ) : (
        <Typography.Text strong>{emptyText}</Typography.Text>
      )}
    </div>
  );
}

function buildBatchColumns(): ColumnsType<IngestBatch> {
  return [
    {
      title: '批次',
      dataIndex: 'id',
      width: 82,
      render: (value) => <Typography.Text strong>#{value}</Typography.Text>,
    },
    {
      title: '数据集',
      dataIndex: 'dataset_name',
      width: 132,
      render: (_, record) => getBatchDataset(record),
    },
    {
      title: '范围',
      key: 'range',
      width: 210,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatIngestBatchRange(record)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(getBatchMarket(record), '全部市场')}
            {getBatchSymbol(record) ? ` / ${getBatchSymbol(record)}` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '实际来源',
      dataIndex: 'source',
      width: 120,
      render: (value) => value || '-',
    },
    {
      title: '请求来源',
      dataIndex: 'requested_source',
      width: 150,
      render: (_, record) => formatTaskSource(getBatchRequestedSource(record)),
    },
    {
      title: '校验',
      dataIndex: 'status',
      width: 112,
      render: (_, record) => <StatusTag value={record.status} />,
    },
    {
      title: '记录',
      key: 'records',
      width: 190,
      render: (_, record) => (
        <Typography.Text>
          原始 {formatNumber(getBatchRawRecords(record))} / 标准化 {formatNumber(getBatchNormalizedRecords(record))} / 写入{' '}
          {formatNumber(getBatchRecordsWritten(record))}
        </Typography.Text>
      ),
    },
    {
      title: '版本',
      key: 'versions',
      width: 150,
      render: (_, record) => (
        <Typography.Text type="secondary">
          schema {getBatchSchemaVersion(record)} / normalize {getBatchNormalizeVersion(record)}
        </Typography.Text>
      ),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 100,
      render: (_, record) => <StatusTag value={getBatchQualityStatus(record)} />,
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 104,
      render: (_, record) =>
        canTraceBatchToStock(record) ? (
          <Link to="/data-system/stocks/$symbol" params={{ symbol: getBatchSymbol(record) ?? '' }}>
            <Button type="link" size="small" icon={<FileTextOutlined />}>
              查看股票
            </Button>
          </Link>
        ) : (
          '-'
        ),
    },
  ];
}

function getSyncEvidenceDecision({
  overview,
  watermarks,
  failedBatches,
}: {
  overview?: DatabaseIntegrationOverview;
  watermarks: SyncWatermark[];
  failedBatches: RecentIngestBatch[];
}) {
  const summary = overview?.summary;
  const coverage = overview?.coverage_summary;
  const repairableWatermark = watermarks.find((watermark) => getWatermarkRepairFocus(watermark, coverage));
  const latestBatch = overview?.recent_batches?.[0];

  if (coverage?.coverage_status === 'degraded') {
    return {
      status: 'warning',
      title: '覆盖率暂不可确认',
      description: coverage.coverage_message ?? 'Parquet / DuckDB 覆盖查询暂不可用，先检查最近批次和 worker 日志。',
      actionLabel: '查看失败批次',
      focus: undefined,
    };
  }

  if ((coverage?.daily_missing_symbol_days ?? 0) > 0) {
    return {
      status: 'warning',
      title: '需要补齐市场日线',
      description: `最近半年缺少 ${formatNumber(coverage?.daily_missing_symbol_days)} 个股票-交易日，优先创建市场级日线缺口补齐任务。`,
      actionLabel: '补齐日线',
      focus: getWatermarkRepairFocus(repairableWatermark ?? watermarks[0], coverage) ?? 'daily-bars-market-repair',
    };
  }

  if (failedBatches.length > 0) {
    return {
      status: 'error',
      title: '存在失败入库批次',
      description: failedBatches[0].error_message || '先打开失败任务，确认 provider、schema 或上游异常。',
      actionLabel: '看失败任务',
      focus: undefined,
    };
  }

  if (!summary || summary.recent_batches_total <= 0) {
    return {
      status: 'default',
      title: '还没有正式入库批次',
      description: '先同步股票池和交易日历，再创建单股日线或市场级补齐任务。',
      actionLabel: '同步股票池',
      focus: 'stock-list',
    };
  }

  return {
    status: 'success',
    title: '最近同步可追溯',
    description: latestBatch
      ? `最近批次 #${latestBatch.id} 写入 ${formatNumber(latestBatch.records_written)} 条，实际来源 ${latestBatch.source || '-'}。`
      : '最近批次、水位线和质量状态已可在下方追溯。',
    actionLabel: '继续补数',
    focus: repairableWatermark ? getWatermarkRepairFocus(repairableWatermark, coverage) : 'daily-bars-market-repair',
  };
}

function SyncConsolePanel({
  total,
  runningCount,
  failedCount,
  status,
  runnerLoading,
  runnerError,
  overview,
  watermarks,
  failedBatches,
  evidenceLoading,
  evidenceError,
  onRefresh,
  onOpenTask,
  onOpenFailedTask,
}: {
  total: number;
  runningCount: number;
  failedCount: number;
  status?: SyncRunnerStatus;
  runnerLoading: boolean;
  runnerError: unknown;
  overview?: DatabaseIntegrationOverview;
  watermarks: SyncWatermark[];
  failedBatches: RecentIngestBatch[];
  evidenceLoading: boolean;
  evidenceError: boolean;
  onRefresh: () => void;
  onOpenTask: (taskId: number) => void;
  onOpenFailedTask: (taskId: number) => void;
}) {
  const summary = overview?.summary;
  const coverage = overview?.coverage_summary;
  const latestBatch = overview?.recent_batches?.[0];
  const fallbackSuccesses = summary?.fallback_successes_total ?? 0;
  const failedTaskId = getNumericTaskId(failedBatches[0]?.task_id);
  const decision = getSyncEvidenceDecision({ overview, watermarks, failedBatches });
  const actionSearch = decision.focus
    ? {
        focus: decision.focus,
        market: coverage?.market ?? DEFAULT_MARKET,
        startDate: coverage?.coverage_start_date ?? undefined,
        endDate: coverage?.coverage_end_date ?? undefined,
        maxSymbols: decision.focus === 'daily-bars-market-repair' ? DEFAULT_MARKET_REPAIR_MAX_SYMBOLS : undefined,
      }
    : undefined;

  return (
    <Card
      className="sync-console-panel stock-detail-panel"
      title={
        <Space size={8}>
          <SyncOutlined />
          <span>同步控制台</span>
        </Space>
      }
      extra={
        <Space size={8} wrap>
          <Tag color={getRunnerStatusColor(status?.status)}>{getRunnerStatusLabel(status?.status)}</Tag>
          <Button size="small" icon={<ReloadOutlined />} loading={runnerLoading || evidenceLoading} onClick={onRefresh}>
            刷新
          </Button>
        </Space>
      }
    >
      <div className="sync-console-grid" aria-busy={runnerLoading || evidenceLoading}>
        <div className="sync-console-decision">
          {evidenceError ? (
            <Alert type="error" showIcon message="同步证据加载失败" description="后端数据库整合总览接口暂不可用。" />
          ) : (
            <>
              <Space wrap size={[8, 8]}>
                <StatusTag value={decision.status} />
                <Tag>{formatMarket(coverage?.market, '中国 A 股')}</Tag>
                {fallbackSuccesses > 0 ? <Tag color="blue">fallback {formatNumber(fallbackSuccesses)} 次</Tag> : null}
              </Space>
              <div>
                <Typography.Title level={4}>{decision.title}</Typography.Title>
                <Typography.Text type="secondary">{decision.description}</Typography.Text>
              </div>
              <Space wrap>
                {failedTaskId && !actionSearch ? (
                  <Button type="primary" danger onClick={() => onOpenFailedTask(failedTaskId)}>
                    {decision.actionLabel}
                  </Button>
                ) : actionSearch ? (
                  <Link to="/data-system/sync-tasks" search={actionSearch}>
                    <Button type="primary">{decision.actionLabel}</Button>
                  </Link>
                ) : null}
              </Space>
            </>
          )}
        </div>

        <div className="sync-console-kpis">
          <Statistic title="任务结果" value={total} prefix={<FileTextOutlined />} />
          <Statistic title="等待/运行" value={runningCount} />
          <Statistic title="失败任务" value={failedCount} />
          <Statistic title="市场缺口" value={coverage?.daily_missing_symbol_days ?? 0} />
          <Statistic title="水位线" value={watermarks.length} />
          <Statistic title="最近批次" value={latestBatch ? `#${latestBatch.id}` : '-'} />
        </div>

        <div className="sync-console-runner">
          {runnerError ? (
            <Alert type="error" showIcon message="执行器状态加载失败" description="后端同步状态接口暂不可用。" />
          ) : (
            <>
              <div className="sync-console-runner-head">
                <Space direction="vertical" size={2}>
                  <Typography.Text type="secondary">执行器</Typography.Text>
                  <Typography.Text strong>{formatRunnerMode(status?.mode)}</Typography.Text>
                </Space>
                <Space size={16} wrap>
                  <Statistic title="待执行" value={status?.pending_count ?? 0} />
                  <Statistic title="运行" value={status?.running_count ?? 0} />
                  <Statistic title="失败" value={status?.failed_count ?? 0} />
                </Space>
              </div>
              <Alert
                type={status?.status === 'warning' || status?.status === 'pending' ? 'warning' : 'info'}
                showIcon
                message={status?.message ?? '正在读取同步执行器状态'}
              />
              {status?.worker_command ? (
                <Typography.Text className="sync-runner-command" code copyable>
                  {status.worker_command}
                </Typography.Text>
              ) : null}
              <div className="sync-console-task-strip">
                <RunnerTaskRefItem label="当前运行" task={status?.current_task} emptyText="暂无运行" onOpenTask={onOpenTask} />
                <RunnerTaskRefItem label="下一条" task={status?.next_pending_task} emptyText="暂无待执行" onOpenTask={onOpenTask} />
                <RunnerTaskRefItem label="最近成功" task={status?.latest_success_task} emptyText="暂无成功" onOpenTask={onOpenTask} />
                <RunnerTaskRefItem label="最近失败" task={status?.latest_failed_task} emptyText="暂无失败" onOpenTask={onOpenTask} />
              </div>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

function buildWatermarkColumns(coverage?: DatabaseCoverageSummary): ColumnsType<SyncWatermark> {
  return [
    {
      title: '数据类型',
      dataIndex: 'dataset_name',
      width: 120,
      render: (value) => <Typography.Text strong>{formatTaskType(value)}</Typography.Text>,
    },
    {
      title: '范围',
      key: 'scope',
      width: 150,
      render: (_, watermark) => formatWatermarkScope(watermark),
    },
    {
      title: '实际来源',
      dataIndex: 'source',
      width: 150,
      render: (_, watermark) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{watermark.source || '-'}</Typography.Text>
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
            <Typography.Text>{formatWatermarkRepairRange(watermark)}</Typography.Text>
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
      width: 180,
      render: (_, watermark) =>
        watermark.last_failed_at || watermark.last_failure_reason ? (
          <Space direction="vertical" size={0}>
            <Typography.Text type="danger">{formatDateTime(watermark.last_failed_at)}</Typography.Text>
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
      width: 96,
      render: (value) => formatNumber(value),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 96,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '最近成功',
      dataIndex: 'last_success_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 126,
      render: (_, watermark) => {
        const focus = getWatermarkRepairFocus(watermark, coverage);
        const failureTaskId = getNumericTaskId(watermark.last_failure_task_id);
        return (
          <Space size={2}>
            {failureTaskId ? (
              <Link to="/data-system/sync-tasks" search={{ taskId: failureTaskId, page: 1, pageSize: DEFAULT_PAGE_SIZE }}>
                <Button type="link" size="small">
                  失败
                </Button>
              </Link>
            ) : null}
            {focus ? (
              <Link to="/data-system/sync-tasks" search={getWatermarkRepairSearch(watermark, coverage)}>
                <Button type="link" size="small">
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

function buildRecentFailureColumns(onOpenTaskId: (taskId: number) => void): ColumnsType<RecentIngestBatch> {
  return [
    {
      title: '批次',
      dataIndex: 'id',
      width: 82,
      render: (value) => <Typography.Text strong>#{value}</Typography.Text>,
    },
    {
      title: '数据类型',
      dataIndex: 'dataset_name',
      width: 120,
      render: (value) => formatTaskType(value),
    },
    {
      title: '范围',
      key: 'range',
      width: 170,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatBatchRange(batch)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(batch.market)}
            {batch.symbol ? ` / ${batch.symbol}` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (value) => value || '-',
    },
    {
      title: '失败原因',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (value) => (
        <Typography.Text type="danger" ellipsis>
          {value || '未记录'}
        </Typography.Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 92,
      render: (_, batch) => {
        const taskId = getNumericTaskId(batch.task_id);
        return taskId ? (
          <Button type="link" size="small" onClick={() => onOpenTaskId(taskId)}>
            详情
          </Button>
        ) : (
          '-'
        );
      },
    },
  ];
}

function buildColumns(onOpenTask: (task: SyncTask) => void): ColumnsType<SyncTask> {
  return [
    {
      title: '任务 ID',
      dataIndex: 'id',
      width: 92,
      render: (value) => <Typography.Text strong>#{value}</Typography.Text>,
    },
    {
      title: '任务类型',
      dataIndex: 'task_type',
      width: 128,
      render: (_, record) => getTaskType(record),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (_, record) => <StatusTag value={record.status} />,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 150,
      render: (_, record) => (
        <Progress percent={Math.max(0, Math.min(100, Number(record.progress ?? 0)))} size="small" />
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 120,
      render: (value) => formatTaskSource(value),
    },
    {
      title: '实际来源',
      key: 'source_evidence',
      width: 170,
      render: (_, record) => renderTaskSourceEvidence(record),
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 110,
      render: (value) => formatMarket(value, '全部市场'),
    },
    {
      title: '读取',
      dataIndex: 'records_read',
      width: 96,
      render: (_, record) => formatNumber(getRecordsRead(record)),
    },
    {
      title: '写入',
      dataIndex: 'records_written',
      width: 96,
      render: (_, record) => formatNumber(getRecordsWritten(record)),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (_, record) => formatDateTime(getCreatedAt(record)),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 92,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => onOpenTask(record)}>
          详情
        </Button>
      ),
    },
  ];
}

export function SyncTasksPage() {
  const { message } = AntApp.useApp();
  const pageRef = useRef<HTMLDivElement>(null);
  const stockCardRef = useRef<HTMLDivElement>(null);
  const dailyBarsCardRef = useRef<HTMLDivElement>(null);
  const calendarCardRef = useRef<HTMLDivElement>(null);
  const search = useSearch({ from: '/data-system/sync-tasks' });
  const navigate = useNavigate({ from: '/data-system/sync-tasks' });
  const [dailyBarsMode, setDailyBarsMode] = useState<DailyBarsMode>(
    search.focus === 'daily-bars-market-repair' ? 'market-repair' : 'single',
  );
  const [operationTab, setOperationTab] = useState<SyncOperationTab>(getSyncOperationTab(search.focus));
  const [stockForm] = Form.useForm<{ source?: string; market?: string }>();
  const [dailyBarsForm] = Form.useForm<{
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
    adjustType?: 'none' | 'qfq' | 'hfq';
  }>();
  const [marketRepairForm] = Form.useForm<MarketRepairFormValues>();
  const [calendarForm] = Form.useForm<{
    source?: string;
    market?: string;
    dateRange?: [Dayjs, Dayjs];
  }>();
  const marketRepairDateRange = Form.useWatch('dateRange', marketRepairForm);

  const params = useMemo<SyncTaskListParams>(
    () => ({
      status: search.status ?? '',
      source: search.source ?? '',
      taskType: search.taskType ?? '',
      market: search.market ?? '',
      symbol: search.symbol ?? '',
      startDate: search.startDate ?? '',
      endDate: search.endDate ?? '',
      page: search.page ?? 1,
      pageSize: search.pageSize ?? DEFAULT_PAGE_SIZE,
    }),
    [
      search.endDate,
      search.market,
      search.page,
      search.pageSize,
      search.source,
      search.startDate,
      search.status,
      search.symbol,
      search.taskType,
    ],
  );

  const selectedTaskId = search.taskId;
  const tasksQuery = useSyncTasksQuery(params);
  const dataSourcesQuery = useDataSourcesQuery();
  const overviewMarket = params.market || DEFAULT_MARKET;
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: overviewMarket });
  const runnerStatusQuery = useSyncRunnerStatusQuery();
  const schedulesQuery = useSyncSchedulesQuery();
  const syncStocksMutation = useSyncStocksMutation();
  const syncDailyBarsMutation = useSyncDailyBarsMutation();
  const syncDailyBarsMarketRepairMutation = useSyncDailyBarsMarketRepairMutation();
  const previewDailyBarsMarketRepairMutation = usePreviewDailyBarsMarketRepairMutation();
  const syncCalendarsMutation = useSyncTradingCalendarsMutation();
  const updateScheduleMutation = useUpdateSyncScheduleMutation();
  const triggerScheduleMutation = useTriggerSyncScheduleMutation();
  const taskQuery = useSyncTaskQuery(selectedTaskId, { refetchWhenActive: true });
  const tasks = tasksQuery.data?.items ?? [];
  const schedules = schedulesQuery.data?.items ?? [];
  const selectedTask = taskQuery.data;
  const selectedTaskIsActive = selectedTask?.status === 'pending' || selectedTask?.status === 'running';
  const logsQuery = useSyncTaskLogsQuery(selectedTaskId, { active: selectedTaskIsActive });
  const batchesQuery = useSyncTaskIngestBatchesQuery(selectedTaskId, { active: selectedTaskIsActive });
  const logs = logsQuery.data?.items ?? [];
  const batches = batchesQuery.data?.items ?? [];
  const integrationOverview = integrationOverviewQuery.data;
  const coverageSummary = integrationOverview?.coverage_summary;
  const watermarks = integrationOverview?.sync_watermarks ?? [];
  const failedBatches = useMemo(
    () => (integrationOverview?.recent_batches ?? []).filter((batch) => batch.status === 'failed').slice(0, 5),
    [integrationOverview?.recent_batches],
  );
  const openTaskDetail = useCallback(
    (taskId: number) => {
      void navigate({
        search: {
          status: params.status || undefined,
          source: params.source || undefined,
          taskType: params.taskType || undefined,
          market: params.market || undefined,
          symbol: params.symbol || undefined,
          startDate: params.startDate || undefined,
          endDate: params.endDate || undefined,
          page: params.page,
          pageSize: params.pageSize,
          taskId,
        },
      });
    },
    [
      navigate,
      params.endDate,
      params.market,
      params.page,
      params.pageSize,
      params.source,
      params.startDate,
      params.status,
      params.symbol,
      params.taskType,
    ],
  );
  const batchColumns = useMemo(() => buildBatchColumns(), []);
  const watermarkColumns = useMemo(() => buildWatermarkColumns(coverageSummary), [coverageSummary]);
  const recentFailureColumns = useMemo(
    () => buildRecentFailureColumns(openTaskDetail),
    [openTaskDetail],
  );
  const runningCount = tasks.filter((task) => task.status === 'pending' || task.status === 'running').length;
  const failedCount = tasks.filter((task) => task.status === 'failed').length;
  const dataSources = dataSourcesQuery.data ?? [];
  const sourceOptionsForCapability = (capability: 'stock_list' | 'daily_bars' | 'calendars') => [
    { label: '自动选择（按优先级）', value: 'auto' },
    ...dataSources
      .filter((source) => source.enabled && getDataSourceCapabilities(source)[capability])
      .map((source) => ({
        label: `${source.name} (${source.code})`,
        value: source.code,
      })),
  ];
  const stockSourceOptions = useMemo(() => sourceOptionsForCapability('stock_list'), [dataSources]);
  const dailyBarsSourceOptions = useMemo(() => sourceOptionsForCapability('daily_bars'), [dataSources]);
  const calendarSourceOptions = useMemo(() => sourceOptionsForCapability('calendars'), [dataSources]);
  const isCreatingTask =
    syncStocksMutation.isPending ||
    syncDailyBarsMutation.isPending ||
    syncDailyBarsMarketRepairMutation.isPending ||
    syncCalendarsMutation.isPending;
  const focusedSyncLabel = search.focus ? syncFocusLabels[search.focus] : undefined;
  const marketRepairDateRangeLabel = useMemo(() => {
    const [startDate, endDate] = marketRepairDateRange ?? [];
    if (!startDate?.isValid() || !endDate?.isValid()) {
      return undefined;
    }
    return `${formatDate(startDate.format('YYYY-MM-DD'))} ~ ${formatDate(endDate.format('YYYY-MM-DD'))}`;
  }, [marketRepairDateRange]);
  const columns = useMemo(
    () =>
      buildColumns((task) => {
        const taskId = Number(task.id);
        if (Number.isFinite(taskId)) {
          openTaskDetail(taskId);
        }
      }),
    [openTaskDetail],
  );

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }

      fadeInUp(root.querySelectorAll('.sync-console-panel, .sync-operations-card, .sync-tracking-card'), {
        stagger: 0.05,
        y: 8,
      });
    },
    { scope: pageRef },
  );

  useEffect(() => {
    setOperationTab(getSyncOperationTab(search.focus));

    const targetRef =
      search.focus === 'stock-list'
        ? stockCardRef
        : search.focus === 'daily-bars' || search.focus === 'daily-bars-market-repair'
          ? dailyBarsCardRef
          : search.focus === 'calendars'
            ? calendarCardRef
            : null;

    if (!targetRef) {
      return;
    }

    window.requestAnimationFrame(() => {
      targetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, [search.focus]);

  useEffect(() => {
    if (search.focus === 'daily-bars-market-repair') {
      setDailyBarsMode('market-repair');
    }
    if (search.focus === 'daily-bars') {
      setDailyBarsMode('single');
    }

    if (search.focus === 'daily-bars') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      dailyBarsForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        symbol: search.symbol ?? '',
        dateRange: startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : undefined,
        adjustType: DEFAULT_ADJUST_TYPE,
      });
    }

    if (search.focus === 'daily-bars-market-repair') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      marketRepairForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        dateRange: getValidDateRangeOrDefault(startDate, endDate),
        maxSymbols: normalizeMarketRepairMaxSymbols(search.maxSymbols),
        startPolicy: DEFAULT_MARKET_REPAIR_START_POLICY,
        adjustType: DEFAULT_ADJUST_TYPE,
      });
    }

    if (search.focus === 'calendars') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      calendarForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        dateRange: startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : undefined,
      });
    }

    if (search.focus === 'stock-list') {
      stockForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
      });
    }
  }, [
    calendarForm,
    dailyBarsForm,
    marketRepairForm,
    search.endDate,
    search.focus,
    search.market,
    search.maxSymbols,
    search.startDate,
    search.symbol,
    search.syncSource,
    stockForm,
  ]);

  const closeDrawer = () => {
    void navigate({
      search: {
        status: params.status || undefined,
        source: params.source || undefined,
        taskType: params.taskType || undefined,
        market: params.market || undefined,
        symbol: params.symbol || undefined,
        startDate: params.startDate || undefined,
        endDate: params.endDate || undefined,
        page: params.page,
        pageSize: params.pageSize,
      },
    });
  };

  const refreshTasks = () => {
    void tasksQuery.refetch();
    void integrationOverviewQuery.refetch();
    void runnerStatusQuery.refetch();
    void schedulesQuery.refetch();
  };

  const notifyTaskCreated = (
    label: string,
    task: SyncTask | undefined,
    nextSearch?: Partial<TaskCreatedSearch>,
  ) => {
    const suffix = task?.id ? ` #${task.id}` : '';
    const taskId = getNumericTaskId(task?.id);
    void message.success(
      taskId
        ? `${label}同步任务已创建并入队${suffix}，已打开任务追踪`
        : `${label}同步任务已创建并入队${suffix}，等待 worker 执行`,
    );
    refreshTasks();
    if (taskId) {
      void navigate({
        search: {
          status: params.status || undefined,
          source: params.source || undefined,
          taskType: params.taskType || undefined,
          market: params.market || undefined,
          symbol: params.symbol || undefined,
          startDate: params.startDate || undefined,
          endDate: params.endDate || undefined,
          page: 1,
          pageSize: params.pageSize,
          ...nextSearch,
          taskId,
        },
      });
    }
  };

  const handleStockSync = (values: { source?: string; market?: string }) => {
    syncStocksMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('股票池', task, {
            focus: 'stock-list',
            market: values.market || DEFAULT_MARKET,
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '股票池同步任务创建失败');
        },
      },
    );
  };

  const handleDailyBarsSync = (values: {
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
    adjustType?: 'none' | 'qfq' | 'hfq';
  }) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    const symbol = values.symbol?.trim();
    if (!symbol) {
      void message.warning('请先填写股票代码');
      return;
    }

    syncDailyBarsMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        symbol,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE,
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('日线行情', task, {
            focus: 'daily-bars',
            taskType: 'daily_bars',
            market: values.market || DEFAULT_MARKET,
            symbol,
            startDate: startDate.format('YYYY-MM-DD'),
            endDate: endDate.format('YYYY-MM-DD'),
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '日线行情同步任务创建失败');
        },
      },
    );
  };

  const handleMarketDailyBarsRepair = (values: MarketRepairFormValues) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    const startPolicy = values.startPolicy || DEFAULT_MARKET_REPAIR_START_POLICY;
    syncDailyBarsMarketRepairMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        max_symbols: normalizeMarketRepairMaxSymbols(values.maxSymbols),
        start_policy: startPolicy,
        adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE,
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('市场级日线缺口补齐', task, {
            focus: 'daily-bars-market-repair',
            taskType: 'daily_bars_market_repair',
            market: values.market || DEFAULT_MARKET,
            symbol: undefined,
            startDate: startDate.format('YYYY-MM-DD'),
            endDate: endDate.format('YYYY-MM-DD'),
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '市场级日线缺口补齐任务创建失败');
        },
      },
    );
  };

  const handleMarketDailyBarsRepairPreview = async () => {
    try {
      const values = await marketRepairForm.validateFields();
      const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
      const startPolicy = values.startPolicy || DEFAULT_MARKET_REPAIR_START_POLICY;
      previewDailyBarsMarketRepairMutation.mutate(
        {
          source: values.source || 'auto',
          market: values.market || DEFAULT_MARKET,
          start_date: startDate.format('YYYY-MM-DD'),
          end_date: endDate.format('YYYY-MM-DD'),
          max_symbols: normalizeMarketRepairMaxSymbols(values.maxSymbols),
          start_policy: startPolicy,
          adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE,
        },
        {
          onError: (error) => {
            void message.error(error instanceof Error ? error.message : '补齐计划预览失败');
          },
        },
      );
    } catch {
      void message.warning('请先完善市场、日期范围和安全上限');
    }
  };

  const handleCalendarSync = (values: { source?: string; market?: string; dateRange?: [Dayjs, Dayjs] }) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    syncCalendarsMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('交易日历', task, {
            focus: 'calendars',
            taskType: 'calendars',
            market: values.market || DEFAULT_MARKET,
            startDate: startDate.format('YYYY-MM-DD'),
            endDate: endDate.format('YYYY-MM-DD'),
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '交易日历同步任务创建失败');
        },
      },
    );
  };

  const handleScheduleToggle = (schedule: SyncSchedule, enabled: boolean) => {
    updateScheduleMutation.mutate(
      {
        code: schedule.code,
        payload: { enabled },
      },
      {
        onSuccess: () => {
          void message.success(enabled ? '定时规则已启用' : '定时规则已停用');
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '定时规则更新失败');
        },
      },
    );
  };

  const handleScheduleSave = (schedule: SyncSchedule, values: ScheduleFormValues) => {
    const symbol = values.symbol?.trim();
    updateScheduleMutation.mutate(
      {
        code: schedule.code,
        payload: {
          source: values.source || 'auto',
          market: values.market || DEFAULT_MARKET,
          symbol: symbol || '',
          cron_expression: values.cron_expression?.trim() || getScheduleCron(schedule),
        },
      },
      {
        onSuccess: () => {
          void message.success('定时规则配置已保存');
          refreshTasks();
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '定时规则配置保存失败');
        },
      },
    );
  };

  const handleScheduleTrigger = (schedule: SyncSchedule) => {
    const scheduleTaskType = getScheduleTaskType(schedule);
    const scheduleCapability = getScheduleCapability(schedule);
    const focus =
      scheduleTaskType === 'daily_bars_market_repair'
        ? 'daily-bars-market-repair'
        : scheduleCapability === 'daily_bars'
          ? 'daily-bars'
          : scheduleCapability;

    triggerScheduleMutation.mutate(
      { code: schedule.code },
      {
        onSuccess: (task) => {
          notifyTaskCreated('定时规则', task, {
            focus,
            taskType: scheduleTaskType,
            market: schedule.market || DEFAULT_MARKET,
            symbol: schedule.symbol || undefined,
            source: schedule.source || undefined,
          });
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '定时规则触发失败');
        },
      },
    );
  };

  const stockListPane = (
    <div className={`sync-operation-pane${search.focus === 'stock-list' ? ' is-focused' : ''}`} ref={stockCardRef}>
      <div className="sync-operation-intro">
        <Space size={8}>
          <SyncOutlined />
          <Typography.Title level={5}>股票池</Typography.Title>
        </Space>
        <Typography.Text type="secondary">从启用来源更新 A 股基础列表，作为日线补齐和交易日历校验的入口数据。</Typography.Text>
      </div>
      <Form
        className="sync-operation-form"
        form={stockForm}
        layout="vertical"
        initialValues={{ source: 'auto', market: DEFAULT_MARKET }}
        onFinish={handleStockSync}
      >
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item label="数据源" name="source">
              <Select options={stockSourceOptions} loading={dataSourcesQuery.isFetching} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="市场" name="market">
              <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={syncStocksMutation.isPending}>
          更新股票池
        </Button>
      </Form>
    </div>
  );

  const dailyBarsPane = (
    <div
      className={`sync-operation-pane sync-operation-pane-primary${
        search.focus === 'daily-bars' || search.focus === 'daily-bars-market-repair' ? ' is-focused' : ''
      }`}
      ref={dailyBarsCardRef}
    >
      <div className="sync-operation-intro">
        <Space size={8}>
          <FileTextOutlined />
          <Typography.Title level={5}>日线同步</Typography.Title>
        </Space>
        <Typography.Text type="secondary">
          {dailyBarsMode === 'single'
            ? '指定单只股票和日期范围，写入标准日线行情与整合批次。'
            : '按市场和日期范围创建受控补齐任务，由后端逐只修复股票-交易日缺口。'}
        </Typography.Text>
      </div>
      <Segmented
        className="sync-operation-mode"
        block
        value={dailyBarsMode}
        onChange={(value) => {
          setDailyBarsMode(value as DailyBarsMode);
          if (value !== 'market-repair') {
            previewDailyBarsMarketRepairMutation.reset();
          }
        }}
        options={[
          { label: '单股日线', value: 'single' },
          { label: '市场缺口补齐', value: 'market-repair' },
        ]}
      />
      {dailyBarsMode === 'single' ? (
        <Form
          className="sync-operation-form"
          form={dailyBarsForm}
          layout="vertical"
          initialValues={{
            source: 'auto',
            market: DEFAULT_MARKET,
            symbol: '',
            dateRange: DEFAULT_DATE_RANGE,
            adjustType: DEFAULT_ADJUST_TYPE,
          }}
          onFinish={handleDailyBarsSync}
        >
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="股票代码" name="symbol" rules={[{ required: true, message: '请输入股票代码' }]}>
                <Input placeholder={`例如 ${SYMBOL_EXAMPLE}`} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="市场" name="market">
                <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker className="full-width-control" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="数据源" name="source">
                <Select options={dailyBarsSourceOptions} loading={dataSourcesQuery.isFetching} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="复权口径" name="adjustType">
            <Segmented block options={adjustTypeOptions} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={syncDailyBarsMutation.isPending}>
            同步单股日线
          </Button>
        </Form>
      ) : (
        <Form
          className="sync-operation-form"
          form={marketRepairForm}
          layout="vertical"
          initialValues={{
            source: 'auto',
            market: DEFAULT_MARKET,
            dateRange: DEFAULT_DATE_RANGE,
            maxSymbols: DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
            startPolicy: DEFAULT_MARKET_REPAIR_START_POLICY,
            adjustType: DEFAULT_ADJUST_TYPE,
          }}
          onFinish={handleMarketDailyBarsRepair}
          onValuesChange={() => previewDailyBarsMarketRepairMutation.reset()}
        >
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="市场" name="market">
                <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label="最大股票数"
                name="maxSymbols"
                rules={[{ required: true, message: '请设置本次最多处理的股票数' }]}
              >
                <InputNumber className="full-width-control" min={1} max={MAX_MARKET_REPAIR_SYMBOLS} precision={0} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="数据源" name="source">
                <Select options={dailyBarsSourceOptions} loading={dataSourcesQuery.isFetching} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker className="full-width-control" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="补齐起点" name="startPolicy">
                <Segmented
                  block
                  options={[
                    { label: '按填写起始日', value: 'requested_start' },
                    { label: '从上市日', value: 'listing_date' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="复权口径" name="adjustType">
            <Segmented block options={adjustTypeOptions} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="市场级补齐不填写股票代码，建议先预览股票池、开市日和缺口计划，再创建任务。"
            description={
              marketRepairDateRangeLabel
                ? `当前补齐范围 ${marketRepairDateRangeLabel}；选择“从上市日”时，每只股票会从上市日与填写起始日中较晚的一天开始补齐。`
                : undefined
            }
          />
          <MarketRepairPreviewPanel
            preview={previewDailyBarsMarketRepairMutation.data}
            loading={previewDailyBarsMarketRepairMutation.isPending}
            error={previewDailyBarsMarketRepairMutation.error}
          />
          <Space className="market-repair-actions">
            <Button loading={previewDailyBarsMarketRepairMutation.isPending} onClick={() => void handleMarketDailyBarsRepairPreview()}>
              预览补齐计划
            </Button>
            <Button type="primary" htmlType="submit" loading={syncDailyBarsMarketRepairMutation.isPending}>
              创建市场补齐任务
            </Button>
          </Space>
        </Form>
      )}
    </div>
  );

  const calendarPane = (
    <div className={`sync-operation-pane${search.focus === 'calendars' ? ' is-focused' : ''}`} ref={calendarCardRef}>
      <div className="sync-operation-intro">
        <Space size={8}>
          <CalendarOutlined />
          <Typography.Title level={5}>交易日历</Typography.Title>
        </Space>
        <Typography.Text type="secondary">补齐交易日历覆盖，供日线缺口检查和后续调度判断使用。</Typography.Text>
      </div>
      <Form
        className="sync-operation-form"
        form={calendarForm}
        layout="vertical"
        initialValues={{ source: 'auto', market: DEFAULT_MARKET, dateRange: DEFAULT_DATE_RANGE }}
        onFinish={handleCalendarSync}
      >
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item label="市场" name="market">
              <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
              <DatePicker.RangePicker className="full-width-control" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="数据源" name="source">
              <Select options={calendarSourceOptions} loading={dataSourcesQuery.isFetching} />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={syncCalendarsMutation.isPending}>
          同步交易日历
        </Button>
      </Form>
    </div>
  );

  const schedulePane = schedulesQuery.isError ? (
    <Alert type="error" showIcon message="定时规则加载失败" description="后端同步计划配置接口暂不可用。" />
  ) : (
    <Row gutter={[12, 12]}>
      {schedules.map((schedule) => (
        <Col span={8} key={schedule.code}>
          <div className="sync-schedule-item">
            <div className="sync-schedule-heading">
              <Typography.Text strong>{schedule.name}</Typography.Text>
              <Space size={8}>
                <Tooltip title={canTriggerSchedule(schedule) ? '按当前规则创建一次同步任务' : '请先在配置规则里填写股票代码'}>
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    disabled={!canTriggerSchedule(schedule)}
                    loading={triggerScheduleMutation.isPending && triggerScheduleMutation.variables?.code === schedule.code}
                    onClick={() => handleScheduleTrigger(schedule)}
                  >
                    立即触发
                  </Button>
                </Tooltip>
                <Switch
                  size="small"
                  checked={schedule.enabled}
                  checkedChildren="启用"
                  unCheckedChildren="停用"
                  loading={updateScheduleMutation.isPending}
                  onChange={(checked) => handleScheduleToggle(schedule, checked)}
                />
              </Space>
            </div>
            <Typography.Text type="secondary">{getScheduleNote(schedule)}</Typography.Text>
            <div className="sync-schedule-meta">
              <Tag color={schedule.enabled ? 'success' : 'default'}>{schedule.enabled ? '已启用' : '未启用'}</Tag>
              <Tag>{getScheduleCron(schedule)}</Tag>
            </div>
            <Typography.Text type="secondary">{getScheduleScope(schedule)}</Typography.Text>
            <Typography.Text type="secondary">最近触发：{formatDateTime(getScheduleLastTriggeredAt(schedule))}</Typography.Text>
            <Collapse
              ghost
              size="small"
              className="sync-schedule-config"
              items={[
                {
                  key: 'config',
                  label: '配置规则',
                  children: (
                    <Form<ScheduleFormValues>
                      layout="vertical"
                      initialValues={getScheduleInitialValues(schedule)}
                      onFinish={(values) => handleScheduleSave(schedule, values)}
                    >
                      <Form.Item label="数据源" name="source">
                        <Select options={sourceOptionsForCapability(getScheduleCapability(schedule))} loading={dataSourcesQuery.isFetching} />
                      </Form.Item>
                      <Row gutter={8}>
                        <Col span={12}>
                          <Form.Item label="市场" name="market">
                            <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item
                            label="股票代码"
                            name="symbol"
                            tooltip={
                              getScheduleTaskType(schedule) === 'daily_bars'
                                ? '第一阶段日线规则需要单只股票代码，后续再扩展全市场批量。'
                                : '股票池和交易日历规则可留空。'
                            }
                          >
                            <Input placeholder={getScheduleTaskType(schedule) === 'daily_bars' ? SYMBOL_EXAMPLE : '可留空'} />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item label="Cron 表达式" name="cron_expression" rules={[{ required: true, message: '请输入 cron 表达式' }]}>
                        <Input placeholder="30 18 * * 1-5" />
                      </Form.Item>
                      <Button size="small" type="primary" htmlType="submit" loading={updateScheduleMutation.isPending} block>
                        保存配置
                      </Button>
                    </Form>
                  ),
                },
              ]}
            />
          </div>
        </Col>
      ))}
      {schedules.length === 0 ? (
        <Col span={24}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无定时规则" />
        </Col>
      ) : null}
    </Row>
  );

  const watermarkPane = (
    <Row gutter={[16, 16]} align="stretch" className="sync-watermark-row">
      <Col span={15}>
        {integrationOverviewQuery.isError ? (
          <Alert type="error" showIcon message="同步水位线加载失败" description="后端数据整合总览接口暂不可用。" />
        ) : (
          <Table<SyncWatermark>
            rowKey={(record) => `${record.dataset_name}-${record.source}-${record.market}-${record.symbol}-${record.batch_id}`}
            columns={watermarkColumns}
            dataSource={watermarks}
            loading={integrationOverviewQuery.isFetching}
            pagination={false}
            size="small"
            scroll={{ x: 1340 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无成功水位线" /> }}
          />
        )}
      </Col>
      <Col span={9}>
        {integrationOverviewQuery.isError ? (
          <Alert type="error" showIcon message="失败批次加载失败" />
        ) : (
          <Table<RecentIngestBatch>
            rowKey={(record) => String(record.id)}
            columns={recentFailureColumns}
            dataSource={failedBatches}
            loading={integrationOverviewQuery.isFetching}
            pagination={false}
            size="small"
            scroll={{ x: 720 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无失败批次" /> }}
          />
        )}
      </Col>
    </Row>
  );

  const recentTasksPane = (
    <>
      <Form
        key={[params.status, params.source, params.taskType, params.market, params.symbol, params.startDate, params.endDate].join('|')}
        className="stock-filters sync-task-filters"
        layout="inline"
        initialValues={{
          status: params.status,
          source: params.source,
          taskType: params.taskType,
          market: params.market,
          symbol: params.symbol,
          dateRange: params.startDate && params.endDate ? [dayjs(params.startDate), dayjs(params.endDate)] : undefined,
        }}
        onFinish={(values: {
          status?: string;
          source?: string;
          taskType?: string;
          market?: string;
          symbol?: string;
          dateRange?: [Dayjs, Dayjs];
        }) => {
          const [startDate, endDate] = values.dateRange ?? [];
          void navigate({
            search: {
              status: values.status || undefined,
              source: values.source?.trim() || undefined,
              taskType: values.taskType || undefined,
              market: values.market || undefined,
              symbol: values.symbol?.trim() || undefined,
              startDate: startDate?.format('YYYY-MM-DD'),
              endDate: endDate?.format('YYYY-MM-DD'),
              page: 1,
              pageSize: params.pageSize,
            },
          });
        }}
      >
        <Form.Item name="status">
          <Select className="filter-select" options={statusOptions} />
        </Form.Item>
        <Form.Item name="taskType">
          <Select className="filter-select" options={taskTypeOptions} />
        </Form.Item>
        <Form.Item name="market">
          <Select
            allowClear
            className="filter-select"
            options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]}
            placeholder="市场"
          />
        </Form.Item>
        <Form.Item name="source" className="filter-keyword">
          <Input allowClear placeholder="数据源，如 akshare" />
        </Form.Item>
        <Form.Item name="symbol" className="filter-keyword">
          <Input allowClear placeholder={`股票代码，如 ${SYMBOL_EXAMPLE}`} />
        </Form.Item>
        <Form.Item name="dateRange">
          <DatePicker.RangePicker className="full-width-control" />
        </Form.Item>
        <Form.Item className="filter-actions">
          <Space wrap>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                void navigate({
                  search: {
                    page: 1,
                    pageSize: params.pageSize,
                  },
                });
              }}
            >
              重置
            </Button>
            <Button icon={<ReloadOutlined />} loading={tasksQuery.isFetching || isCreatingTask} onClick={refreshTasks}>
              刷新
            </Button>
          </Space>
        </Form.Item>
      </Form>

      {tasksQuery.isError ? (
        <ErrorState error={tasksQuery.error} onRetry={() => void tasksQuery.refetch()} />
      ) : (
        <Table<SyncTask>
          className="sync-tasks-table"
          rowKey={(record) => String(record.id)}
          columns={columns}
          dataSource={tasks}
          loading={tasksQuery.isFetching}
          scroll={{ x: 1290 }}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无同步记录" />,
          }}
          pagination={{
            current: params.page,
            pageSize: params.pageSize,
            total: tasksQuery.data?.total ?? 0,
            showSizeChanger: false,
            showTotal: (totalValue, range) => `${range[0]}-${range[1]} / 共 ${totalValue} 条`,
            onChange: (page, pageSize) => {
              void navigate({
                search: {
                  status: params.status || undefined,
                  source: params.source || undefined,
                  taskType: params.taskType || undefined,
                  market: params.market || undefined,
                  symbol: params.symbol || undefined,
                  startDate: params.startDate || undefined,
                  endDate: params.endDate || undefined,
                  page,
                  pageSize,
                  taskId: selectedTaskId,
                },
              });
            },
          }}
        />
      )}
    </>
  );

  const syncOperationItems = [
    { key: 'daily-bars', label: '日线补齐', children: dailyBarsPane },
    { key: 'stock-list', label: '股票池', children: stockListPane },
    { key: 'calendars', label: '交易日历', children: calendarPane },
  ];

  const trackingItems = [
    { key: 'recent', label: '最近记录', children: recentTasksPane },
    { key: 'watermarks', label: '水位线与失败', children: watermarkPane },
    { key: 'schedules', label: '定时规则', children: schedulePane },
  ];

  return (
    <div className="workbench sync-tasks-page" ref={pageRef}>
      <div className="workbench-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>同步调度</Typography.Title>
          <Typography.Text type="secondary">数据系统 / 手动同步、后续定时计划、任务状态与日志</Typography.Text>
        </Space>
      </div>

      <SyncConsolePanelCard
        total={tasksQuery.data?.total ?? 0}
        runningCount={runningCount}
        failedCount={failedCount}
        status={runnerStatusQuery.data}
        runnerLoading={runnerStatusQuery.isFetching}
        runnerError={runnerStatusQuery.isError ? runnerStatusQuery.error : null}
        overview={integrationOverview}
        watermarks={watermarks}
        failedBatches={failedBatches}
        evidenceLoading={integrationOverviewQuery.isFetching}
        evidenceError={integrationOverviewQuery.isError}
        onRefresh={refreshTasks}
        onOpenTask={openTaskDetail}
        onOpenFailedTask={openTaskDetail}
      />

      {focusedSyncLabel ? (
        <Alert
          className="sync-focus-alert"
          type="info"
          showIcon
          message={`已定位到${focusedSyncLabel}`}
          description={
            search.focus === 'daily-bars'
              ? '第一版日线同步按单只股票创建任务；如从水位线进入且没有股票代码，请先在数据库管理确认缺口范围。'
              : '可直接确认数据源、市场和日期范围后创建同步任务；任务创建后会进入最近同步记录和同步水位线。'
          }
        />
      ) : null}

      <SyncOperationTabsCard
        searchFocus={search.focus}
        activeTab={operationTab}
        onTabChange={(tab) => setOperationTab(tab === 'daily-bars' ? 'daily-bars' : (tab as SyncOperationTab))}
        dailyBarsMode={dailyBarsMode}
        onDailyBarsModeChange={setDailyBarsMode}
        onResetMarketRepairPreview={() => previewDailyBarsMarketRepairMutation.reset()}
        stockCardRef={stockCardRef}
        dailyBarsCardRef={dailyBarsCardRef}
        calendarCardRef={calendarCardRef}
        stockForm={stockForm}
        dailyBarsForm={dailyBarsForm}
        marketRepairForm={marketRepairForm}
        calendarForm={calendarForm}
        stockSourceOptions={stockSourceOptions}
        dailyBarsSourceOptions={dailyBarsSourceOptions}
        calendarSourceOptions={calendarSourceOptions}
        dataSourcesLoading={dataSourcesQuery.isFetching}
        previewDailyBarsMarketRepairData={previewDailyBarsMarketRepairMutation.data}
        previewDailyBarsMarketRepairLoading={previewDailyBarsMarketRepairMutation.isPending}
        previewDailyBarsMarketRepairError={previewDailyBarsMarketRepairMutation.error}
        isCreatingTask={isCreatingTask}
        onStockSync={handleStockSync}
        onDailyBarsSync={handleDailyBarsSync}
        onMarketDailyBarsRepair={handleMarketDailyBarsRepair}
        onMarketDailyBarsRepairPreview={() => void handleMarketDailyBarsRepairPreview()}
        onCalendarSync={handleCalendarSync}
      />

      <Card className="sync-tracking-card stock-detail-panel" title="运行追踪">
        <Tabs defaultActiveKey="recent" items={trackingItems} />
      </Card>
      <SyncTaskDetailDrawer
        taskId={selectedTaskId}
        task={selectedTask}
        batches={batches}
        logs={logs}
        taskLoading={taskQuery.isFetching}
        batchesLoading={batchesQuery.isFetching}
        logsLoading={logsQuery.isFetching}
        taskError={taskQuery.isError}
        batchesError={batchesQuery.isError}
        logsError={logsQuery.isError}
        onClose={closeDrawer}
      />
    </div>
  );
}
