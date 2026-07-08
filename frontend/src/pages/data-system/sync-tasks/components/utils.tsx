/**
 * Constants and utility functions extracted from SyncTasksPage.
 */
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { Space, Tag, Typography } from 'antd';
import type { DataSource } from '../../../../features/data-sources/types';
import type {
  RecentIngestBatch,
  SyncWatermark,
  DatabaseCoverageSummary,
} from '../../../../features/database/types';
import type { SyncTask, SyncTaskLog, IngestBatch, SyncSchedule, SyncRunnerTaskRef, SyncTaskListParams } from '../../../../features/sync-tasks/types';
import { formatDate, formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { formatMarket, formatTaskType, formatSourceMode } from '../../../../shared/domain/labels';


export const DEFAULT_PAGE_SIZE = 10;
export const DEFAULT_MARKET = 'A_SHARE';
export const SYMBOL_EXAMPLE = '600519';
export const DEFAULT_DATE_RANGE: [Dayjs, Dayjs] = [dayjs().subtract(90, 'day'), dayjs()];
export const DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20;
export const MAX_MARKET_REPAIR_SYMBOLS = 200;
export const DEFAULT_MARKET_REPAIR_START_POLICY = 'requested_start';
export const DEFAULT_ADJUST_TYPE: 'none' | 'qfq' | 'hfq' = 'none';
export const adjustTypeOptions = [
  { label: '不复权', value: 'none' },
  { label: '前复权', value: 'qfq' },
  { label: '后复权', value: 'hfq' },
];
export const syncFocusLabels: Record<string, string> = {
  'stock-list': '手动同步股票池',
  'daily-bars': '手动同步日线',
  'daily-bars-market-repair': '市场级日线缺口补齐',
  calendars: '交易日历同步',
};

export type DailyBarsMode = 'single' | 'market-repair';
export type SyncOperationTab = 'daily-bars' | 'stock-list' | 'calendars';

export type MarketRepairFormValues = {
  source?: string;
  market?: string;
  dateRange?: [Dayjs, Dayjs];
  maxSymbols?: number;
  startPolicy?: 'requested_start' | 'listing_date';
  adjustType?: 'none' | 'qfq' | 'hfq';
};

export type TaskCreatedSearch = Pick<
  SyncTaskListParams,
  'status' | 'source' | 'taskType' | 'market' | 'symbol' | 'startDate' | 'endDate' | 'page' | 'pageSize'
> & {
  focus?: string;
  taskId?: number;
};

export type ScheduleFormValues = {
  source?: string;
  market?: string;
  symbol?: string;
  cron_expression?: string;
};

export const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '等待中', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
];

export const taskTypeOptions = [
  { label: '全部类型', value: '' },
  { label: formatTaskType('stock_list'), value: 'stock_list' },
  { label: formatTaskType('daily_bars'), value: 'daily_bars' },
  { label: formatTaskType('daily_bars_market_repair'), value: 'daily_bars_market_repair' },
  { label: formatTaskType('calendars'), value: 'calendars' },
];


export function getTaskType(task?: SyncTask | null) {
  const type = task?.task_type ?? task?.taskType ?? '-';
  return formatTaskType(type);
}
export function normalizeMarketRepairMaxSymbols(value?: number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_MARKET_REPAIR_MAX_SYMBOLS;
  }
  return Math.min(MAX_MARKET_REPAIR_SYMBOLS, Math.max(1, Math.trunc(numeric)));
}

export function getRecordsRead(task?: SyncTask | null) {
  return task?.records_read ?? task?.recordsRead ?? 0;
}

export function getRecordsWritten(task?: SyncTask | null) {
  return task?.records_written ?? task?.recordsWritten ?? 0;
}

export function getErrorMessage(task?: SyncTask | null) {
  return task?.error_message ?? task?.errorMessage;
}

export function getCreatedAt(task?: SyncTask | null) {
  return task?.created_at ?? task?.createdAt;
}

export function getStartedAt(task?: SyncTask | null) {
  return task?.started_at ?? task?.startedAt;
}

export function getFinishedAt(task?: SyncTask | null) {
  return task?.finished_at ?? task?.finishedAt;
}

export function getTaskCandidateSources(task?: SyncTask | null) {
  const sources = task?.candidate_sources ?? task?.candidateSources ?? [];
  return Array.isArray(sources) ? sources.filter((source): source is string => Boolean(source?.trim())) : [];
}

export function getTaskSelectedSource(task?: SyncTask | null) {
  const source = task?.selected_source ?? task?.selectedSource;
  return source?.trim() || null;
}

export function getDataSourceCapabilities(source: DataSource) {
  return source.capabilities ?? source.config_json?.capabilities ?? {};
}

export function getLogPayload(log: SyncTaskLog) {
  return log.payload_json ?? log.payloadJson;
}

export function getLogTime(log: SyncTaskLog) {
  return log.created_at ?? log.createdAt;
}

export function getBatchDataset(batch: IngestBatch) {
  return batch.dataset_name ?? batch.datasetName ?? '-';
}

export function getBatchRequestedSource(batch: IngestBatch) {
  return batch.requested_source ?? batch.requestedSource;
}

export function getBatchMarket(batch: IngestBatch) {
  return batch.market;
}

export function getBatchSymbol(batch: IngestBatch) {
  return batch.symbol;
}

export function getBatchStartDate(batch: IngestBatch) {
  return batch.start_date ?? batch.startDate;
}

export function getBatchEndDate(batch: IngestBatch) {
  return batch.end_date ?? batch.endDate;
}

export function getBatchSchemaVersion(batch: IngestBatch) {
  return batch.schema_version ?? batch.schemaVersion ?? '-';
}

export function getBatchNormalizeVersion(batch: IngestBatch) {
  return batch.normalize_version ?? batch.normalizeVersion ?? '-';
}

export function getBatchRawRecords(batch: IngestBatch) {
  return batch.raw_records ?? batch.rawRecords ?? 0;
}

export function getBatchNormalizedRecords(batch: IngestBatch) {
  return batch.normalized_records ?? batch.normalizedRecords ?? 0;
}

export function getBatchRecordsWritten(batch: IngestBatch) {
  return batch.records_written ?? batch.recordsWritten ?? 0;
}

export function getBatchValidationErrors(batch: IngestBatch) {
  return batch.validation_errors_json ?? batch.validationErrorsJson ?? [];
}

export function getBatchErrorMessage(batch: IngestBatch) {
  return batch.error_message ?? batch.errorMessage;
}

export function getBatchQualityStatus(batch: IngestBatch) {
  return batch.quality_status ?? batch.qualityStatus ?? '-';
}

export function getBatchStartedAt(batch: IngestBatch) {
  return batch.started_at ?? batch.startedAt;
}

export function getBatchFinishedAt(batch: IngestBatch) {
  return batch.finished_at ?? batch.finishedAt;
}

export function formatTaskSource(value?: string | null) {
  return value === 'auto' ? formatSourceMode(value) : value || '-';
}

export function renderTaskSourceEvidence(task?: SyncTask | null) {
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

export function formatWatermarkScope(watermark: SyncWatermark) {
  const market = formatMarket(watermark.market);
  return watermark.symbol ? `${market} / ${watermark.symbol}` : market;
}

export function formatWatermarkRepairRange(watermark: SyncWatermark) {
  if (!watermark.repair_start_date && !watermark.repair_end_date) {
    return '-';
  }
  if (watermark.repair_start_date && watermark.repair_end_date && watermark.repair_start_date !== watermark.repair_end_date) {
    return `${formatDate(watermark.repair_start_date)} ~ ${formatDate(watermark.repair_end_date)}`;
  }
  return formatDate(watermark.repair_end_date ?? watermark.repair_start_date);
}

export function isMarketDailyRepairHint(watermark: SyncWatermark) {
  return watermark.dataset_name === 'daily_bars' && watermark.repair_reason?.includes('该市场同区间日线');
}

export function getWatermarkRepairFocus(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
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

export function getWatermarkRepairSearch(watermark: SyncWatermark, coverage?: DatabaseCoverageSummary) {
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

export function formatBatchRange(batch: RecentIngestBatch) {
  if (!batch.start_date && !batch.end_date) {
    return '-';
  }
  if (batch.start_date && batch.end_date && batch.start_date !== batch.end_date) {
    return `${formatDate(batch.start_date)} ~ ${formatDate(batch.end_date)}`;
  }
  return formatDate(batch.end_date ?? batch.start_date);
}

export function formatIngestBatchRange(batch: IngestBatch) {
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

export function canTraceBatchToStock(batch: IngestBatch) {
  return getBatchDataset(batch) === 'daily_bars' && Boolean(getBatchSymbol(batch));
}

export function getNumericTaskId(value?: string | number | null) {
  const taskId = Number(value);
  return Number.isFinite(taskId) && taskId > 0 ? taskId : undefined;
}

export function getRunnerTaskType(task?: SyncRunnerTaskRef) {
  return task?.task_type ?? task?.taskType;
}

export function getRunnerTaskStatus(task?: SyncRunnerTaskRef) {
  return task?.status;
}

export function getRunnerTaskCreatedAt(task?: SyncRunnerTaskRef) {
  return task?.created_at ?? task?.createdAt;
}

export function getRunnerTaskStartedAt(task?: SyncRunnerTaskRef) {
  return task?.started_at ?? task?.startedAt;
}

export function getRunnerTaskFinishedAt(task?: SyncRunnerTaskRef) {
  return task?.finished_at ?? task?.finishedAt;
}

export function getRunnerTaskPrimaryTime(task?: SyncRunnerTaskRef) {
  return getRunnerTaskFinishedAt(task) ?? getRunnerTaskStartedAt(task) ?? getRunnerTaskCreatedAt(task);
}

export function formatPayload(payload?: Record<string, unknown> | null) {
  if (!payload || Object.keys(payload).length === 0) {
    return '';
  }

  return JSON.stringify(payload);
}

export function compactValues(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value && value !== '-'))));
}

export function latestLogMessage(logs: SyncTaskLog[]) {
  const errorLog = [...logs].reverse().find((log) => log.level === 'error');
  const latestLog = logs[logs.length - 1];
  return errorLog?.message ?? latestLog?.message;
}

export function summarizeTaskBatches(batches: IngestBatch[]) {
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

export function formatValueList(values: string[], fallback = '-') {
  return values.length ? values.join(' / ') : fallback;
}

export function formatMarketRepairStartPolicy(value?: string | null) {
  return value === 'listing_date' ? '从上市日起' : '按填写起始日';
}

export function getValidDateRangeOrDefault(startDate?: Dayjs, endDate?: Dayjs): [Dayjs, Dayjs] {
  return startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : DEFAULT_DATE_RANGE;
}

export function getSyncOperationTab(focus?: string): SyncOperationTab {
  if (focus === 'stock-list') {
    return 'stock-list';
  }
  if (focus === 'calendars') {
    return 'calendars';
  }
  return 'daily-bars';
}


export function getScheduleTaskType(schedule: SyncSchedule) {
  return schedule.task_type ?? schedule.taskType ?? '-';
}

export function getScheduleCron(schedule: SyncSchedule) {
  return schedule.cron_expression ?? schedule.cronExpression ?? '-';
}

export function getScheduleNote(schedule: SyncSchedule) {
  return schedule.schedule_note ?? schedule.scheduleNote ?? '';
}

export function getScheduleLastTriggeredAt(schedule: SyncSchedule) {
  return schedule.last_triggered_at ?? schedule.lastTriggeredAt;
}

export function getScheduleInitialValues(schedule: SyncSchedule): ScheduleFormValues {
  return {
    source: schedule.source || 'auto',
    market: schedule.market || DEFAULT_MARKET,
    symbol: schedule.symbol ?? '',
    cron_expression: getScheduleCron(schedule),
  };
}

export function getScheduleScope(schedule: SyncSchedule) {
  const parts = [formatTaskType(getScheduleTaskType(schedule)), formatMarket(schedule.market), formatTaskSource(schedule.source)];
  if (schedule.symbol) {
    parts.splice(2, 0, schedule.symbol);
  }
  return parts.filter(Boolean).join(' / ');
}

export function formatRunnerMode(value?: string | null) {
  if (value === 'lightweight_worker') {
    return '轻量 worker';
  }
  return value || '-';
}

export function getRunnerStatusColor(status?: string) {
  if (status === 'running') {
    return 'processing';
  }
  if (status === 'pending' || status === 'warning') {
    return 'warning';
  }
  return 'success';
}

export function getRunnerStatusLabel(status?: string) {
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

export function getTaskStatusLabel(status?: string | null) {
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

export function getScheduleCapability(schedule: SyncSchedule): 'stock_list' | 'daily_bars' | 'calendars' {
  const taskType = getScheduleTaskType(schedule);
  if (taskType === 'daily_bars' || taskType === 'daily_bars_market_repair') {
    return 'daily_bars';
  }
  if (taskType === 'calendars') {
    return 'calendars';
  }
  return 'stock_list';
}

export function canTriggerSchedule(schedule: SyncSchedule) {
  return getScheduleTaskType(schedule) !== 'daily_bars' || Boolean(schedule.symbol);
}

