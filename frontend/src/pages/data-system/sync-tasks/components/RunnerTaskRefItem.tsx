/**
 * RunnerTaskRefItem component extracted from SyncTasksPage.
 */
import { Button, Space, Typography } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import { StatusTag } from '../../../../shared/components/StatusTag';
import { formatTaskType } from '../../../../shared/domain/labels';
import { formatDateTime } from '../../../../shared/components/formatters';
import type { SyncRunnerTaskRef } from '../../../../features/sync-tasks/types';
import {
  getRunnerTaskType, getRunnerTaskStatus,
  getRunnerTaskPrimaryTime,
  getNumericTaskId,
} from './utils';

export function RunnerTaskRefItem({
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

