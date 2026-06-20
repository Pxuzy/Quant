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
import { formatLogLevel, formatMarket, formatSourceMode, formatTaskType } from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

const DEFAULT_PAGE_SIZE = 10;
const DEFAULT_MARKET = 'A_SHARE';
const SYMBOL_EXAMPLE = '600519';
const DEFAULT_DATE_RANGE: [Dayjs, Dayjs] = [dayjs().subtract(90, 'day'), dayjs()];
const DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20;
const MAX_MARKET_REPAIR_SYMBOLS = 200;
const syncFocusLabels: Record<string, string> = {
  'stock-list': '手动同步股票池',
  'daily-bars': '手动同步日线',
  'daily-bars-market-repair': '市场级日线缺口补齐',
  calendars: '交易日历同步',
};

type DailyBarsMode = 'single' | 'market-repair';

type MarketRepairFormValues = {
  source?: string;
  market?: string;
  dateRange?: [Dayjs, Dayjs];
  maxSymbols?: number;
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

function RunnerStatusPanel({
  status,
  loading,
  error,
  onRefresh,
  onOpenTask,
}: {
  status?: SyncRunnerStatus;
  loading: boolean;
  error: unknown;
  onRefresh: () => void;
  onOpenTask: (taskId: number) => void;
}) {
  return (
    <Card
      className="sync-runner-card stock-detail-panel"
      title="同步执行器状态"
      extra={
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
          刷新
        </Button>
      }
    >
      {error ? (
        <Alert type="error" showIcon message="执行器状态加载失败" description="后端同步状态接口暂不可用。" />
      ) : (
        <Space className="sync-runner-layout" direction="vertical" size={14}>
          <div className="sync-runner-head">
            <Space direction="vertical" size={4}>
              <Tag color={getRunnerStatusColor(status?.status)}>{getRunnerStatusLabel(status?.status)}</Tag>
              <Typography.Text strong>{formatRunnerMode(status?.mode)}</Typography.Text>
            </Space>
            <Space size={18} wrap>
              <Statistic title="等待" value={status?.pending_count ?? 0} />
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
            <div className="sync-runner-worker">
              <Space direction="vertical" size={8}>
                <Typography.Text type="secondary">{status.worker_note ?? '创建任务后，请启动本地轻量 worker 执行待处理任务。'}</Typography.Text>
                <Typography.Text className="sync-runner-command" code copyable>
                  {status.worker_command}
                </Typography.Text>
                {status.supported_task_types?.length ? (
                  <Space size={[6, 6]} wrap>
                    <Typography.Text type="secondary">支持任务</Typography.Text>
                    {status.supported_task_types.map((taskType) => (
                      <Tag key={taskType}>{formatTaskType(taskType)}</Tag>
                    ))}
                  </Space>
                ) : null}
              </Space>
            </div>
          ) : null}
          <div className="sync-runner-task-grid">
            <RunnerTaskRefItem
              label="当前运行"
              task={status?.current_task}
              emptyText="暂无运行中任务"
              onOpenTask={onOpenTask}
            />
            <RunnerTaskRefItem
              label="下一条待执行"
              task={status?.next_pending_task}
              emptyText="暂无待执行任务"
              onOpenTask={onOpenTask}
            />
            <RunnerTaskRefItem
              label="最近成功"
              task={status?.latest_success_task}
              emptyText="暂无成功记录"
              onOpenTask={onOpenTask}
            />
            <RunnerTaskRefItem
              label="最近失败"
              task={status?.latest_failed_task}
              emptyText="暂无失败记录"
              onOpenTask={onOpenTask}
            />
          </div>
          <div className="sync-runner-meta">
            <div>
              <Typography.Text type="secondary">定时规则</Typography.Text>
              <Typography.Text strong>
                {formatNumber(status?.enabled_schedules ?? 0)} / {formatNumber(status?.total_schedules ?? 0)} 已启用
              </Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">最近创建任务</Typography.Text>
              <Typography.Text strong>
                {status?.latest_task_id ? `#${status.latest_task_id} / ${getTaskStatusLabel(status.latest_task_status)}` : '-'}
              </Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">最近创建</Typography.Text>
              <Typography.Text strong>{formatDateTime(status?.latest_task_created_at)}</Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">最近 worker 活动</Typography.Text>
              <Typography.Text strong>{formatDateTime(status?.latest_worker_activity_at)}</Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">最近定时触发</Typography.Text>
              <Typography.Text strong>{formatDateTime(status?.latest_triggered_at)}</Typography.Text>
            </div>
          </div>
        </Space>
      )}
    </Card>
  );
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

function SyncEvidencePanel({
  overview,
  watermarks,
  failedBatches,
  loading,
  error,
  onOpenFailedTask,
}: {
  overview?: DatabaseIntegrationOverview;
  watermarks: SyncWatermark[];
  failedBatches: RecentIngestBatch[];
  loading: boolean;
  error: boolean;
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
    <Card className="sync-evidence-card stock-detail-panel" title="执行证据总览">
      {error ? (
        <Alert type="error" showIcon message="同步证据加载失败" description="后端数据库整合总览接口暂不可用。" />
      ) : (
        <Space className="sync-evidence-layout" direction="vertical" size={14}>
          <div className="sync-evidence-decision">
            <Space direction="vertical" size={8}>
              <Space wrap size={[8, 8]}>
                <StatusTag value={decision.status} />
                <Tag>{formatMarket(coverage?.market, '中国 A 股')}</Tag>
                {fallbackSuccesses > 0 ? <Tag color="blue">fallback {formatNumber(fallbackSuccesses)} 次</Tag> : null}
              </Space>
              <div>
                <Typography.Title level={5}>{decision.title}</Typography.Title>
                <Typography.Text type="secondary">{decision.description}</Typography.Text>
              </div>
            </Space>
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
          </div>
          <div className="sync-evidence-grid" aria-busy={loading}>
            <div>
              <Typography.Text type="secondary">最近批次</Typography.Text>
              <Typography.Text strong>{latestBatch ? `#${latestBatch.id}` : '-'}</Typography.Text>
              <Typography.Text type="secondary">
                {latestBatch
                  ? `${formatTaskType(latestBatch.dataset_name)} / ${formatNumber(latestBatch.records_written)} 条`
                  : '暂无正式写入'}
              </Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">缺口规模</Typography.Text>
              <Typography.Text strong>{formatNumber(coverage?.daily_missing_symbol_days ?? 0)}</Typography.Text>
              <Typography.Text type="secondary">
                覆盖 {formatNumber(coverage?.daily_covered_stock_count ?? 0)} / {formatNumber(coverage?.stock_pool_total ?? 0)} 只
              </Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">失败批次</Typography.Text>
              <Typography.Text strong>{formatNumber(summary?.failed_batches_total ?? failedBatches.length)}</Typography.Text>
              <Typography.Text type="secondary">{failedBatches[0]?.error_message || '暂无最近失败'}</Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">同步水位线</Typography.Text>
              <Typography.Text strong>{formatNumber(watermarks.length)}</Typography.Text>
              <Typography.Text type="secondary">记录最新成功、失败和待补范围</Typography.Text>
            </div>
          </div>
        </Space>
      )}
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
  const [stockForm] = Form.useForm<{ source?: string; market?: string }>();
  const [dailyBarsForm] = Form.useForm<{
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
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

      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.05, y: 8 });

      const tableCard = root.querySelector('.sync-table-card');
      if (tableCard) {
        fadeInUp(tableCard, { delay: 0.08, y: 8 });
      }
    },
    { scope: pageRef },
  );

  useEffect(() => {
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
      });
    }

    if (search.focus === 'daily-bars-market-repair') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      marketRepairForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        dateRange: startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : undefined,
        maxSymbols: normalizeMarketRepairMaxSymbols(search.maxSymbols),
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

  const handleMarketDailyBarsRepair = (values: {
    source?: string;
    market?: string;
    dateRange?: [Dayjs, Dayjs];
    maxSymbols?: number;
  }) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    syncDailyBarsMarketRepairMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        max_symbols: normalizeMarketRepairMaxSymbols(values.maxSymbols),
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
      previewDailyBarsMarketRepairMutation.mutate(
        {
          source: values.source || 'auto',
          market: values.market || DEFAULT_MARKET,
          start_date: startDate.format('YYYY-MM-DD'),
          end_date: endDate.format('YYYY-MM-DD'),
          max_symbols: normalizeMarketRepairMaxSymbols(values.maxSymbols),
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

  return (
    <div className="workbench sync-tasks-page" ref={pageRef}>
      <div className="workbench-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>同步调度</Typography.Title>
          <Typography.Text type="secondary">数据系统 / 手动同步、后续定时计划、任务状态与日志</Typography.Text>
        </Space>
      </div>

      <Row gutter={[16, 16]} className="summary-row">
        <Col xs={24} sm={8}>
          <Card className="motion-summary-card">
            <Statistic title="当前结果" value={tasksQuery.data?.total ?? 0} prefix={<SyncOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card className="motion-summary-card">
            <Statistic title="等待/运行" value={runningCount} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card className="motion-summary-card">
            <Statistic title="失败任务" value={failedCount} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
      </Row>

      <RunnerStatusPanel
        status={runnerStatusQuery.data}
        loading={runnerStatusQuery.isFetching}
        error={runnerStatusQuery.isError ? runnerStatusQuery.error : null}
        onRefresh={() => void runnerStatusQuery.refetch()}
        onOpenTask={openTaskDetail}
      />

      <SyncEvidencePanel
        overview={integrationOverview}
        watermarks={watermarks}
        failedBatches={failedBatches}
        loading={integrationOverviewQuery.isFetching}
        error={integrationOverviewQuery.isError}
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

      <Row gutter={[16, 16]} align="stretch" className="sync-command-row">
        <Col span={8}>
          <div ref={stockCardRef}>
            <Card
              className={`sync-command-card stock-detail-panel${search.focus === 'stock-list' ? ' is-focused' : ''}`}
              title="手动同步股票池"
              extra={<SyncOutlined />}
            >
              <Typography.Text type="secondary">
                从 AKShare、BaoStock、AData、Tushare、Stock SDK 等启用来源更新 A 股基础列表。
              </Typography.Text>
              <Form
                form={stockForm}
                layout="vertical"
                initialValues={{ source: 'auto', market: DEFAULT_MARKET }}
                onFinish={handleStockSync}
              >
                <Form.Item label="数据源" name="source">
                  <Select options={stockSourceOptions} loading={dataSourcesQuery.isFetching} />
                </Form.Item>
                <Form.Item label="市场" name="market">
                  <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={syncStocksMutation.isPending} block>
                  更新股票池
                </Button>
              </Form>
            </Card>
          </div>
        </Col>

        <Col span={8}>
          <div ref={dailyBarsCardRef}>
            <Card
              className={`sync-command-card stock-detail-panel${
                search.focus === 'daily-bars' || search.focus === 'daily-bars-market-repair' ? ' is-focused' : ''
              }`}
              title="日线同步"
              extra={<FileTextOutlined />}
            >
              <Typography.Text type="secondary">
                {dailyBarsMode === 'single'
                  ? '指定单只股票和日期范围，写入标准日线行情与整合批次。'
                  : '按市场和日期范围创建受控补齐任务，由后端根据股票池和已有日线数据逐只修复缺口。'}
              </Typography.Text>
              <Segmented
                className="full-width-control"
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
                  form={dailyBarsForm}
                  layout="vertical"
                  initialValues={{
                    source: 'auto',
                    market: DEFAULT_MARKET,
                    symbol: '',
                    dateRange: DEFAULT_DATE_RANGE,
                  }}
                  onFinish={handleDailyBarsSync}
                >
                  <Row gutter={10}>
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
                  <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                    <DatePicker.RangePicker className="full-width-control" />
                  </Form.Item>
                  <Form.Item label="数据源" name="source">
                    <Select options={dailyBarsSourceOptions} loading={dataSourcesQuery.isFetching} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={syncDailyBarsMutation.isPending} block>
                    同步单股日线
                  </Button>
                </Form>
              ) : (
                <Form
                  form={marketRepairForm}
                  layout="vertical"
                  initialValues={{
                    source: 'auto',
                    market: DEFAULT_MARKET,
                    dateRange: DEFAULT_DATE_RANGE,
                    maxSymbols: DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
                  }}
                  onFinish={handleMarketDailyBarsRepair}
                  onValuesChange={() => previewDailyBarsMarketRepairMutation.reset()}
                >
                  <Row gutter={10}>
                    <Col span={12}>
                      <Form.Item label="市场" name="market">
                        <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        label="最大股票数"
                        name="maxSymbols"
                        rules={[{ required: true, message: '请设置本次最多处理的股票数' }]}
                      >
                        <InputNumber className="full-width-control" min={1} max={MAX_MARKET_REPAIR_SYMBOLS} precision={0} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                    <DatePicker.RangePicker className="full-width-control" />
                  </Form.Item>
                  <Form.Item label="数据源" name="source">
                    <Select options={dailyBarsSourceOptions} loading={dataSourcesQuery.isFetching} />
                  </Form.Item>
                  <Alert
                    type="info"
                    showIcon
                    message="市场级补齐不填写股票代码，建议先预览股票池、开市日和缺口计划，再创建任务。"
                    description={
                      marketRepairDateRangeLabel
                        ? `当前补齐范围 ${marketRepairDateRangeLabel}，用于补齐最近半年市场级股票-交易日缺口。`
                        : undefined
                    }
                  />
                  <MarketRepairPreviewPanel
                    preview={previewDailyBarsMarketRepairMutation.data}
                    loading={previewDailyBarsMarketRepairMutation.isPending}
                    error={previewDailyBarsMarketRepairMutation.error}
                  />
                  <Space className="market-repair-actions">
                    <Button
                      loading={previewDailyBarsMarketRepairMutation.isPending}
                      onClick={() => void handleMarketDailyBarsRepairPreview()}
                    >
                      预览补齐计划
                    </Button>
                    <Button type="primary" htmlType="submit" loading={syncDailyBarsMarketRepairMutation.isPending}>
                      创建市场补齐任务
                    </Button>
                  </Space>
                </Form>
              )}
            </Card>
          </div>
        </Col>

        <Col span={8}>
          <div ref={calendarCardRef}>
            <Card
              className={`sync-command-card stock-detail-panel${search.focus === 'calendars' ? ' is-focused' : ''}`}
              title="交易日历同步"
              extra={<CalendarOutlined />}
            >
              <Typography.Text type="secondary">
                补齐交易日历覆盖，供日线缺口检查和后续调度判断使用。
              </Typography.Text>
              <Form
                form={calendarForm}
                layout="vertical"
                initialValues={{ source: 'auto', market: DEFAULT_MARKET, dateRange: DEFAULT_DATE_RANGE }}
                onFinish={handleCalendarSync}
              >
                <Form.Item label="市场" name="market">
                  <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
                </Form.Item>
                <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                  <DatePicker.RangePicker className="full-width-control" />
                </Form.Item>
                <Form.Item label="数据源" name="source">
                  <Select options={calendarSourceOptions} loading={dataSourcesQuery.isFetching} />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={syncCalendarsMutation.isPending} block>
                  同步交易日历
                </Button>
              </Form>
            </Card>
          </div>
        </Col>
      </Row>

      <Card
        className="sync-schedule-card stock-detail-panel"
        title="定时规则"
        extra={<Typography.Text type="secondary">自动 cron 暂未启用，可手动触发规则</Typography.Text>}
      >
        {schedulesQuery.isError ? (
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
                  <Typography.Text type="secondary">
                    最近触发：{formatDateTime(getScheduleLastTriggeredAt(schedule))}
                  </Typography.Text>
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
                              <Select
                                options={sourceOptionsForCapability(getScheduleCapability(schedule))}
                                loading={dataSourcesQuery.isFetching}
                              />
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
                            <Form.Item
                              label="Cron 表达式"
                              name="cron_expression"
                              rules={[{ required: true, message: '请输入 cron 表达式' }]}
                            >
                              <Input placeholder="30 18 * * 1-5" />
                            </Form.Item>
                            <Button
                              size="small"
                              type="primary"
                              htmlType="submit"
                              loading={updateScheduleMutation.isPending}
                              block
                            >
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
        )}
      </Card>

      <Row gutter={[16, 16]} align="stretch" className="sync-watermark-row">
        <Col span={15}>
          <Card className="sync-watermark-card stock-detail-panel" title="同步水位线">
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
          </Card>
        </Col>
        <Col span={9}>
          <Card className="sync-watermark-card stock-detail-panel" title="失败批次">
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
          </Card>
        </Col>
      </Row>

      <Card className="sync-table-card" title="最近同步记录">
        <Form
          key={[
            params.status,
            params.source,
            params.taskType,
            params.market,
            params.symbol,
            params.startDate,
            params.endDate,
          ].join('|')}
          className="stock-filters sync-task-filters"
          layout="inline"
          initialValues={{
            status: params.status,
            source: params.source,
            taskType: params.taskType,
            market: params.market,
            symbol: params.symbol,
            dateRange:
              params.startDate && params.endDate
                ? [dayjs(params.startDate), dayjs(params.endDate)]
                : undefined,
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
              showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${total} 条`,
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
      </Card>

      <Drawer
        title={selectedTaskId ? `同步记录 #${selectedTaskId}` : '同步记录详情'}
        open={Boolean(selectedTaskId)}
        width={620}
        onClose={closeDrawer}
      >
        {taskQuery.isError ? (
          <Alert type="error" showIcon message="任务详情加载失败" description="任务可能不存在或后端接口暂不可用。" />
        ) : (
          <Space className="task-detail-drawer" direction="vertical" size={16}>
            <TaskExecutionSummaryPanel
              task={selectedTask}
              batches={batches}
              logs={logs}
              loading={taskQuery.isFetching || batchesQuery.isFetching || logsQuery.isFetching}
            />

            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="任务类型">{getTaskType(selectedTask)}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusTag value={selectedTask?.status} />
              </Descriptions.Item>
              <Descriptions.Item label="数据源">{formatTaskSource(selectedTask?.source)}</Descriptions.Item>
              <Descriptions.Item label="来源决策">{renderTaskSourceEvidence(selectedTask)}</Descriptions.Item>
              <Descriptions.Item label="市场">{formatMarket(selectedTask?.market, '全部市场')}</Descriptions.Item>
              <Descriptions.Item label="读取记录">{formatNumber(getRecordsRead(selectedTask))}</Descriptions.Item>
              <Descriptions.Item label="写入记录">{formatNumber(getRecordsWritten(selectedTask))}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(getCreatedAt(selectedTask))}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(getStartedAt(selectedTask))}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(getFinishedAt(selectedTask))}</Descriptions.Item>
              {getErrorMessage(selectedTask) ? (
                <Descriptions.Item label="错误信息">
                  <Typography.Text type="danger">{getErrorMessage(selectedTask)}</Typography.Text>
                </Descriptions.Item>
              ) : null}
            </Descriptions>

            <div>
              <Typography.Title level={5}>数据整合批次</Typography.Title>
              {batchesQuery.isError ? (
                <Alert type="error" showIcon message="批次信息加载失败" />
              ) : batches.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据整合批次" />
              ) : (
                <Table<IngestBatch>
                  className="task-ingest-batches-table"
                  rowKey={(record) => String(record.id)}
                  columns={batchColumns}
                  dataSource={batches}
                  loading={batchesQuery.isFetching}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1350 }}
                  expandable={{
                    expandedRowRender: (record) => {
                      const validationErrors = getBatchValidationErrors(record);
                      const errorMessage = getBatchErrorMessage(record);
                      if (!validationErrors.length && !errorMessage) {
                        return <Typography.Text type="secondary">校验通过，无错误信息。</Typography.Text>;
                      }
                      return (
                        <Space direction="vertical" size={4}>
                          {errorMessage ? <Typography.Text type="danger">{errorMessage}</Typography.Text> : null}
                          {validationErrors.map((error) => (
                            <Typography.Text key={error} code>
                              {error}
                            </Typography.Text>
                          ))}
                        </Space>
                      );
                    },
                  }}
                />
              )}
            </div>

            <div>
              <Typography.Title level={5}>执行日志</Typography.Title>
              {logsQuery.isError ? (
                <Alert type="error" showIcon message="任务日志加载失败" />
              ) : logs.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务日志" />
              ) : (
                <Timeline
                  className="task-log-timeline"
                  items={logs.map((log) => {
                    const payload = formatPayload(getLogPayload(log));
                    return {
                      color: log.level === 'error' ? 'red' : 'blue',
                      children: (
                        <Space direction="vertical" size={4}>
                          <Space className="task-log-heading">
                            <Typography.Text strong>{log.message}</Typography.Text>
                            <Typography.Text type="secondary">{formatLogLevel(log.level)}</Typography.Text>
                          </Space>
                          <Typography.Text type="secondary">{formatDateTime(getLogTime(log))}</Typography.Text>
                          {payload ? <Typography.Text code>{payload}</Typography.Text> : null}
                        </Space>
                      ),
                    };
                  })}
                />
              )}
            </div>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
