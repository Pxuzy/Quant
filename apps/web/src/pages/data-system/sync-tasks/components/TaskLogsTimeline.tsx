import { Empty, Space, Timeline, Typography } from 'antd';

import type { SyncTaskLog } from '../../../../features/sync-tasks/types';
import { formatDateTime } from '../../../../shared/components/formatters';
import { formatLogLevel } from '../../../../shared/domain/labels';

function getLogPayload(log: SyncTaskLog) {
  return log.payload_json ?? log.payloadJson;
}

function getLogTime(log: SyncTaskLog) {
  return log.created_at ?? log.createdAt;
}

function formatPayload(payload?: Record<string, unknown> | null) {
  if (!payload || Object.keys(payload).length === 0) {
    return '';
  }
  return JSON.stringify(payload);
}

type TaskLogsTimelineProps = {
  logs: SyncTaskLog[];
  loading: boolean;
  error: boolean;
};

export function TaskLogsTimeline({ logs, loading, error }: TaskLogsTimelineProps) {
  if (error) {
    return (
      <div>
        <Typography.Title level={5}>执行日志</Typography.Title>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="任务日志加载失败" />
      </div>
    );
  }

  return (
    <div>
      <Typography.Title level={5}>执行日志</Typography.Title>
      {logs.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务日志" />
      ) : (
        <Timeline
          className="task-log-timeline"
          pending={loading ? '加载中...' : undefined}
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
  );
}
