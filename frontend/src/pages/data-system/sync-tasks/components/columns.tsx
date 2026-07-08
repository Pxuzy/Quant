/**
 * Column builder functions extracted from SyncTasksPage.
 */
import { Link } from '@tanstack/react-router';
import { Button, Space, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DataSource } from '../../../../features/data-sources/types';
import type { SyncTask, IngestBatch } from '../../../../features/sync-tasks/types';
import type {
  RecentIngestBatch,
  SyncWatermark,
  DatabaseCoverageSummary,
  DatabaseIntegrationOverview,
} from '../../../../features/database/types';
import type { DailyBarsMarketRepairPreviewResponse } from '../../../../features/market-data/types';
import { formatDate, formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { formatMarket, formatTaskType } from '../../../../shared/domain/labels';
import { StatusTag } from '../../../../shared/components/StatusTag';
import {
  getTaskType, getRecordsRead, getRecordsWritten, getErrorMessage,
  getCreatedAt, getStartedAt, getFinishedAt,
  getTaskCandidateSources, getTaskSelectedSource,
  getDataSourceCapabilities, getLogPayload, getLogTime,
  formatTaskSource, renderTaskSourceEvidence,
  formatWatermarkScope, formatWatermarkRepairRange,
  isMarketDailyRepairHint, getWatermarkRepairFocus, getWatermarkRepairSearch,
  formatBatchRange, formatIngestBatchRange, canTraceBatchToStock,
  getNumericTaskId, getRunnerTaskType, getRunnerTaskStatus,
  getRunnerTaskCreatedAt, getRunnerTaskStartedAt, getRunnerTaskFinishedAt,
  getRunnerTaskPrimaryTime, formatPayload, compactValues, latestLogMessage,
  summarizeTaskBatches, formatValueList, formatMarketRepairStartPolicy,
  getValidDateRangeOrDefault, getSyncOperationTab,
  getScheduleTaskType, getScheduleCron, getScheduleNote,
  getScheduleLastTriggeredAt, getScheduleInitialValues, getScheduleScope,
  formatRunnerMode, getRunnerStatusColor, getRunnerStatusLabel,
  getTaskStatusLabel, getScheduleCapability, canTriggerSchedule,
  getBatchDataset, getBatchMarket, getBatchSymbol, getBatchStartDate, getBatchEndDate,
  getBatchRawRecords, getBatchNormalizedRecords, getBatchRecordsWritten,
  getBatchValidationErrors, getBatchErrorMessage, getBatchQualityStatus,
  getBatchStartedAt, getBatchFinishedAt, getBatchSchemaVersion, getBatchNormalizeVersion,
  getBatchRequestedSource,
  DEFAULT_PAGE_SIZE,
} from './utils';
import { Progress } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';

export function buildMarketRepairPreviewColumns(): ColumnsType<NonNullable<DailyBarsMarketRepairPreviewResponse['sample_items']>[number]> {
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

export function buildBatchColumns(): ColumnsType<IngestBatch> {
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

export function getSyncEvidenceDecision({
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

export function buildWatermarkColumns(coverage?: DatabaseCoverageSummary): ColumnsType<SyncWatermark> {
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

export function buildRecentFailureColumns(onOpenTaskId: (taskId: number) => void): ColumnsType<RecentIngestBatch> {
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

export function buildColumns(onOpenTask: (task: SyncTask) => void): ColumnsType<SyncTask> {
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

