import { Alert, Descriptions, Drawer, Space, Typography } from 'antd';

import type { IngestBatch, SyncTask, SyncTaskLog } from '../../../../features/sync-tasks/types';
import { formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { StatusTag } from '../../../../shared/components/StatusTag';
import { formatMarket, formatSourceMode, formatTaskType } from '../../../../shared/domain/labels';
import { TaskBatchesTable } from './TaskBatchesTable';
import { TaskExecutionSummaryPanel } from './TaskExecutionSummaryPanel';
import { TaskLogsTimeline } from './TaskLogsTimeline';

function getTaskType(task?: SyncTask | null) {
  const type = task?.task_type ?? task?.taskType ?? '-';
  return formatTaskType(type);
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

type TaskDetailDrawerProps = {
  taskId?: number;
  task?: SyncTask;
  batches: IngestBatch[];
  logs: SyncTaskLog[];
  taskLoading: boolean;
  batchesLoading: boolean;
  logsLoading: boolean;
  taskError: boolean;
  batchesError: boolean;
  logsError: boolean;
  onClose: () => void;
};

export function TaskDetailDrawer({
  taskId,
  task,
  batches,
  logs,
  taskLoading,
  batchesLoading,
  logsLoading,
  taskError,
  batchesError,
  logsError,
  onClose,
}: TaskDetailDrawerProps) {
  return (
    <Drawer title={taskId ? `同步记录 #${taskId}` : '同步记录详情'} open={Boolean(taskId)} width={620} onClose={onClose}>
      {taskError ? (
        <Alert type="error" showIcon message="任务详情加载失败" description="任务可能不存在或后端接口暂不可用。" />
      ) : (
        <Space className="task-detail-drawer" direction="vertical" size={16}>
          <TaskExecutionSummaryPanel task={task} batches={batches} logs={logs} loading={taskLoading || batchesLoading || logsLoading} />

          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="任务类型">{getTaskType(task)}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <StatusTag value={task?.status} />
            </Descriptions.Item>
            <Descriptions.Item label="数据源">{formatTaskSource(task?.source)}</Descriptions.Item>
            <Descriptions.Item label="来源决策">{renderTaskSourceEvidence(task)}</Descriptions.Item>
            <Descriptions.Item label="市场">{formatMarket(task?.market, '全部市场')}</Descriptions.Item>
            <Descriptions.Item label="读取记录">{formatNumber(getRecordsRead(task))}</Descriptions.Item>
            <Descriptions.Item label="写入记录">{formatNumber(getRecordsWritten(task))}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDateTime(getCreatedAt(task))}</Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatDateTime(getStartedAt(task))}</Descriptions.Item>
            <Descriptions.Item label="结束时间">{formatDateTime(getFinishedAt(task))}</Descriptions.Item>
            {getErrorMessage(task) ? (
              <Descriptions.Item label="错误信息">
                <Typography.Text type="danger">{getErrorMessage(task)}</Typography.Text>
              </Descriptions.Item>
            ) : null}
          </Descriptions>

          <TaskBatchesTable task={task} batches={batches} loading={batchesLoading} error={batchesError} />

          <TaskLogsTimeline logs={logs} loading={logsLoading} error={logsError} />
        </Space>
      )}
    </Drawer>
  );
}
