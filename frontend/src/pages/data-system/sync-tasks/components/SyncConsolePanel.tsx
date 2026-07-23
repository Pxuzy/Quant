import { Link } from '@tanstack/react-router';
import { FileTextOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Space, Statistic, Tag, Typography } from 'antd';

import type { DatabaseIntegrationOverview, RecentIngestBatch, SyncWatermark } from '../../../../features/database/types';
import type { SyncRunnerStatus, SyncRunnerTaskRef } from '../../../../features/sync-tasks/types';
import { formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { StatusTag } from '../../../../shared/components/StatusTag';
import { formatMarket, formatTaskType } from '../../../../shared/domain/labels';

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

function formatRunnerMode(value?: string | null) {
  return value === 'lightweight_worker' ? '轻量 worker' : value || '-';
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

function isMarketRepairWatermark(watermark: SyncWatermark) {
  return watermark.dataset_name === 'daily_bars' && Boolean(watermark.repair_start_date && watermark.repair_end_date);
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
  const repairableWatermark = watermarks.find((watermark) => isMarketRepairWatermark(watermark));
  const latestBatch = overview?.recent_batches?.[0];

  if (coverage?.coverage_status === 'degraded') {
    return {
      status: 'warning',
      title: '覆盖率暂不可确认',
      description: coverage.coverage_message ?? 'Parquet / DuckDB 覆盖查询暂不可用，先检查最近批次和 worker 日志。',
      actionLabel: '查看失败批次',
      focus: undefined as string | undefined,
    };
  }

  if ((coverage?.daily_missing_symbol_days ?? 0) > 0) {
    return {
      status: 'warning',
      title: '需要补齐市场日线',
      description: `最近半年缺少 ${formatNumber(coverage?.daily_missing_symbol_days)} 个股票-交易日，优先创建市场级日线缺口补齐任务。`,
      actionLabel: '补齐日线',
      focus: 'daily-bars-market-repair',
    };
  }

  if (failedBatches.length > 0) {
    return {
      status: 'error',
      title: '存在失败入库批次',
      description: failedBatches[0].error_message || '先打开失败任务，确认 provider、schema 或上游异常。',
      actionLabel: '看失败任务',
      focus: undefined as string | undefined,
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
    focus: repairableWatermark ? 'daily-bars-market-repair' : 'daily-bars-market-repair',
  };
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

type SyncConsolePanelProps = {
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
};

export function SyncConsolePanel({
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
}: SyncConsolePanelProps) {
  const summary = overview?.summary;
  const coverage = overview?.coverage_summary;
  const latestBatch = overview?.recent_batches?.[0];
  const fallbackSuccesses = summary?.fallback_successes_total ?? 0;
  const failedTaskId = getNumericTaskId(failedBatches[0]?.task_id);
  const decision = getSyncEvidenceDecision({ overview, watermarks, failedBatches });
  const actionSearch = decision.focus
    ? {
        focus: decision.focus,
        market: coverage?.market ?? 'A_SHARE',
        startDate: coverage?.coverage_start_date ?? undefined,
        endDate: coverage?.coverage_end_date ?? undefined,
        maxSymbols: decision.focus === 'daily-bars-market-repair' ? 20 : undefined,
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
                  <Link to="/sync-tasks" search={actionSearch}>
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
