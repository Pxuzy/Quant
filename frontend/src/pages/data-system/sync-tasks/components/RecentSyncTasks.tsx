import { useRef } from 'react';
import { ClockCircleOutlined } from '@ant-design/icons';
import { Alert, Empty, List, Progress, Skeleton, Space, Typography } from 'antd';
import { useSyncTasksQuery } from '../../../../features/sync-tasks/api';
import type { SyncTask } from '../../../../features/sync-tasks/types';
import { formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { StatusTag } from '../../../../shared/components/StatusTag';
import { formatMarket, formatTaskType } from '../../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../../shared/motion/gsapMotion';

function getTaskTime(task: SyncTask) {
  return task.created_at ?? task.createdAt ?? task.started_at ?? task.startedAt;
}

function getTaskTitle(task: SyncTask) {
  const type = task.task_type ?? task.taskType ?? 'sync';
  return formatTaskType(type);
}

function getRecordsWritten(task: SyncTask) {
  return task.records_written ?? task.recordsWritten;
}

function getErrorMessage(task: SyncTask) {
  return task.error_message ?? task.errorMessage;
}

function summarizeError(message: string) {
  const lowerMessage = message.toLowerCase();
  if (
    lowerMessage.includes('timeout') ||
    lowerMessage.includes('remote end closed') ||
    lowerMessage.includes('connection') ||
    lowerMessage.includes('httpsconnectionpool')
  ) {
    return '上游接口连接失败，可在同步调度详情中查看完整错误。';
  }

  const firstCause = message.split(';')[0]?.trim() || message;
  return firstCause.length > 80 ? `${firstCause.slice(0, 77)}...` : firstCause;
}

export function RecentSyncTasks() {
  const panelRef = useRef<HTMLDivElement>(null);
  const query = useSyncTasksQuery({ page: 1, pageSize: 6 });
  const tasks = query.data?.items ?? [];
  const taskMotionKey = tasks
    .map((task) => `${task.id}:${task.status}:${task.progress ?? ''}`)
    .join('|');

  useGSAP(
    () => {
      const root = panelRef.current;
      if (!root) {
        return;
      }

      const taskItems = root.querySelectorAll('.task-list .ant-list-item');
      if (taskItems.length > 0) {
        fadeInUp(taskItems, { duration: 0.24, stagger: 0.025, y: 6 });
      }
    },
    {
      dependencies: [query.isLoading, query.isError, taskMotionKey],
      scope: panelRef,
      revertOnUpdate: true,
    },
  );

  if (query.isLoading) {
    return (
      <div className="tasks-panel" ref={panelRef}>
        <Typography.Title level={5}>最近同步记录</Typography.Title>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="tasks-panel" ref={panelRef}>
        <Typography.Title level={5}>最近同步记录</Typography.Title>
        <Alert type="error" showIcon message="任务状态加载失败" description="后端任务接口暂不可用。" />
      </div>
    );
  }

  return (
    <div className="tasks-panel" ref={panelRef}>
      <div className="panel-heading">
        <div>
          <Typography.Title level={5}>最近同步记录</Typography.Title>
          <Typography.Text type="secondary">展示最新任务状态与写入结果</Typography.Text>
        </div>
      </div>

      {tasks.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无同步记录" />
      ) : (
        <List
          className="task-list"
          itemLayout="vertical"
          dataSource={tasks}
          renderItem={(task) => {
            const progress = task.progress ?? (task.status === 'success' ? 100 : 0);
            const errorMessage = getErrorMessage(task);

            return (
              <List.Item>
                <Space className="task-line" align="start" direction="vertical" size={8}>
                  <Space className="task-title" align="center">
                    <Typography.Text strong>{getTaskTitle(task)}</Typography.Text>
                    <StatusTag value={task.status} />
                  </Space>
                  <Space className="task-meta" split={<span className="meta-dot" />}>
                    <span>{formatMarket(task.market, '全部市场')}</span>
                    <span>写入 {formatNumber(getRecordsWritten(task))}</span>
                  </Space>
                  <Progress
                    percent={Math.max(0, Math.min(100, Number(progress)))}
                    size="small"
                    status={task.status === 'failed' ? 'exception' : undefined}
                  />
                  {errorMessage ? (
                    <Typography.Text className="task-error" type="danger">
                      {summarizeError(errorMessage)}
                    </Typography.Text>
                  ) : null}
                  <Space className="task-time">
                    <ClockCircleOutlined />
                    <Typography.Text type="secondary">{formatDateTime(getTaskTime(task))}</Typography.Text>
                  </Space>
                </Space>
              </List.Item>
            );
          }}
        />
      )}
    </div>
  );
}
