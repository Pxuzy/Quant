import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import { Button, Card, Descriptions, Empty, Progress, Space, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CloudSyncOutlined, DatabaseOutlined, ReloadOutlined, SyncOutlined, ToolOutlined } from '@ant-design/icons';
import { useSyncRunnerStatusQuery, useSyncTasksQuery } from '../../../features/sync-tasks/api';
import type { SyncRunnerStatus, SyncTask } from '../../../features/sync-tasks/types';

const RECENT_TASKS_PARAMS = { page: 1, pageSize: 5 };

function getTaskType(task: SyncTask | { task_type?: string | null; taskType?: string | null }) {
  return task.task_type ?? task.taskType ?? '-';
}

function formatTaskType(value?: string | null) {
  const labels: Record<string, string> = {
    stock_list: '股票池',
    daily_bars: '单股日线',
    daily_bars_market_repair: '市场补齐',
    calendars: '交易日历',
  };
  return value ? labels[value] ?? value : '-';
}

function getStatusColor(status?: string | null) {
  if (status === 'running' || status === 'pending') return 'processing';
  if (status === 'success' || status === 'idle') return 'success';
  if (status === 'failed' || status === 'warning') return 'error';
  return 'default';
}

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function formatNumber(value?: number | null) {
  return typeof value === 'number' ? value.toLocaleString('zh-CN') : '0';
}

function getTaskProgress(task: SyncTask) {
  return Math.max(0, Math.min(100, Number(task.progress ?? 0)));
}

function getRecordsWritten(task: SyncTask) {
  return task.records_written ?? task.recordsWritten ?? 0;
}

function supportedTaskTypes(status?: SyncRunnerStatus) {
  return status?.supported_task_types?.map(formatTaskType).join(' / ') || '-';
}

const taskColumns: ColumnsType<SyncTask> = [
  {
    title: '任务',
    dataIndex: 'id',
    width: 90,
    render: (value) => <Typography.Text strong>#{value}</Typography.Text>,
  },
  {
    title: '类型',
    key: 'task_type',
    width: 130,
    render: (_, record) => formatTaskType(getTaskType(record)),
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 110,
    render: (value) => <Tag color={getStatusColor(value)}>{value}</Tag>,
  },
  {
    title: '进度',
    dataIndex: 'progress',
    width: 160,
    render: (_, record) => <Progress percent={getTaskProgress(record)} size="small" />,
  },
  {
    title: '写入',
    key: 'records_written',
    width: 110,
    render: (_, record) => formatNumber(getRecordsWritten(record)),
  },
  {
    title: '创建时间',
    key: 'created_at',
    render: (_, record) => formatDateTime(record.created_at ?? record.createdAt),
  },
  {
    title: '详情',
    key: 'action',
    width: 90,
    render: (_, record) => (
      <Link to="/data-system/sync-tasks" search={{ taskId: Number(record.id), page: 1, pageSize: 10 }}>
        <Button type="link" size="small">
          查看
        </Button>
      </Link>
    ),
  },
];

export function PipelinePage() {
  const runnerStatusQuery = useSyncRunnerStatusQuery();
  const tasksQuery = useSyncTasksQuery(RECENT_TASKS_PARAMS);
  const runnerStatus = runnerStatusQuery.data;
  const recentTasks = tasksQuery.data?.items ?? [];
  const isRefreshing = runnerStatusQuery.isFetching || tasksQuery.isFetching;
  const activeCount = useMemo(
    () => (runnerStatus?.pending_count ?? 0) + (runnerStatus?.running_count ?? 0),
    [runnerStatus?.pending_count, runnerStatus?.running_count],
  );

  const refresh = () => {
    void runnerStatusQuery.refetch();
    void tasksQuery.refetch();
  };

  return (
    <div style={{ padding: 24, maxWidth: 1120 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
          <div>
            <Typography.Title level={4} style={{ marginBottom: 4 }}>
              <DatabaseOutlined /> 数据管线管理
            </Typography.Title>
            <Typography.Text type="secondary">SyncTask / worker / ingest batches</Typography.Text>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={isRefreshing}>
              刷新
            </Button>
            <Link to="/data-system/sync-tasks">
              <Button type="primary" icon={<CloudSyncOutlined />}>
                同步调度
              </Button>
            </Link>
          </Space>
        </Space>

        <Space size={12} wrap>
          <Card style={{ width: 180 }}>
            <Statistic title="待执行 / 执行中" value={activeCount} />
          </Card>
          <Card style={{ width: 180 }}>
            <Statistic title="最近成功" value={runnerStatus?.success_count ?? 0} />
          </Card>
          <Card style={{ width: 180 }}>
            <Statistic title="最近失败" value={runnerStatus?.failed_count ?? 0} />
          </Card>
          <Card style={{ width: 180 }}>
            <Statistic
              title="启用调度"
              value={runnerStatus?.enabled_schedules ?? 0}
              suffix={`/ ${runnerStatus?.total_schedules ?? 0}`}
            />
          </Card>
        </Space>

        <Card
          title="Worker 状态"
          extra={<Tag color={getStatusColor(runnerStatus?.status)}>{runnerStatus?.status ?? 'unknown'}</Tag>}
          loading={runnerStatusQuery.isLoading}
        >
          <Descriptions column={1} size="small">
            <Descriptions.Item label="模式">{runnerStatus?.mode ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="消息">{runnerStatus?.message ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="支持任务">{supportedTaskTypes(runnerStatus)}</Descriptions.Item>
            <Descriptions.Item label="Worker 命令">{runnerStatus?.worker_command ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="Worker 说明">{runnerStatus?.worker_note ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="最近活动">{formatDateTime(runnerStatus?.latest_worker_activity_at)}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="正式入口">
          <Space wrap>
            <Link to="/data-system/sync-tasks" search={{ focus: 'stock-list' }}>
              <Button icon={<CloudSyncOutlined />}>股票池同步</Button>
            </Link>
            <Link to="/data-system/sync-tasks" search={{ focus: 'daily-bars' }}>
              <Button icon={<SyncOutlined />}>单股日线同步</Button>
            </Link>
            <Link to="/data-system/sync-tasks" search={{ focus: 'daily-bars-market-repair' }}>
              <Button icon={<ToolOutlined />}>市场日线补齐</Button>
            </Link>
            <Link to="/data-system/sync-tasks" search={{ focus: 'calendars' }}>
              <Button icon={<DatabaseOutlined />}>交易日历同步</Button>
            </Link>
          </Space>
        </Card>

        <Card title="最近同步任务">
          <Table<SyncTask>
            rowKey="id"
            columns={taskColumns}
            dataSource={recentTasks}
            loading={tasksQuery.isLoading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无同步任务" /> }}
            size="small"
          />
        </Card>
      </Space>
    </div>
  );
}

export default PipelinePage;
