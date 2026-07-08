import { Alert, Space, Tag, Typography } from 'antd';

import type { IngestBatch, SyncTask, SyncTaskLog } from '../../../../features/sync-tasks/types';
import { formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { StatusTag } from '../../../../shared/components/StatusTag';

function getTaskType(task?: SyncTask | null) {
  return task?.task_type ?? task?.taskType ?? '-';
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

function getStartedAt(task?: SyncTask | null) {
  return task?.started_at ?? task?.startedAt;
}

function getFinishedAt(task?: SyncTask | null) {
  return task?.finished_at ?? task?.finishedAt;
}

function compactValues(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value && value !== '-'))));
}

function getBatchDataset(batch: IngestBatch) {
  return batch.dataset_name ?? batch.datasetName ?? '-';
}

function getBatchRequestedSource(batch: IngestBatch) {
  return batch.requested_source ?? batch.requestedSource;
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

function getBatchQualityStatus(batch: IngestBatch) {
  return batch.quality_status ?? batch.qualityStatus ?? '-';
}

function getBatchStartedAt(batch: IngestBatch) {
  return batch.started_at ?? batch.startedAt;
}

function getBatchFinishedAt(batch: IngestBatch) {
  return batch.finished_at ?? batch.finishedAt;
}

function summarizeTaskBatches(batches: IngestBatch[]) {
  const successCount = batches.filter((batch) => batch.status === 'success').length;
  const failedCount = batches.filter((batch) => batch.status === 'failed').length;
  const rawRecords = batches.reduce((sum, batch) => sum + getBatchRawRecords(batch), 0);
  const normalizedRecords = batches.reduce((sum, batch) => sum + getBatchNormalizedRecords(batch), 0);
  const writtenRecords = batches.reduce((sum, batch) => sum + getBatchRecordsWritten(batch), 0);
  const errorMessages = batches.map((batch) => batch.error_message ?? batch.errorMessage).filter((message): message is string => Boolean(message));
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

function latestLogMessage(logs: SyncTaskLog[]) {
  const errorLog = [...logs].reverse().find((log) => log.level === 'error');
  const latestLog = logs[logs.length - 1];
  return errorLog?.message ?? latestLog?.message;
}

type TaskExecutionSummaryPanelProps = {
  task?: SyncTask;
  batches: IngestBatch[];
  logs: SyncTaskLog[];
  loading: boolean;
};

export function TaskExecutionSummaryPanel({ task, batches, logs, loading }: TaskExecutionSummaryPanelProps) {
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
          {summary.requestedSources.length ? <Tag>请求 {formatValueList(summary.requestedSources)}</Tag> : null}
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
            {formatDateTime(summary.firstStartedAt || getStartedAt(task))} ~ {formatDateTime(summary.lastFinishedAt || getFinishedAt(task))}
          </Typography.Text>
        </div>
      </div>
    </div>
  );
}
