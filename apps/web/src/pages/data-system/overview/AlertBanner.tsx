import { Alert, Space, Tag, Typography } from 'antd';
import { WarningOutlined } from '@ant-design/icons';

export type AlertItem = {
  key: string;
  title: string;
  description: string;
  status: 'error' | 'warning' | 'info';
};

export function AlertBanner({
  alerts,
  loading,
}: {
  alerts: AlertItem[];
  loading?: boolean;
}) {
  if (loading) return null;
  if (alerts.length === 0) {
    return (
      <Alert
        type="success"
        showIcon
        message="当前没有需要立即处理的异常"
        description="数据源、同步任务、批次和质量错误处于可接受状态。"
        style={{ marginBottom: 16 }}
      />
    );
  }

  const statusColor = {
    error: 'red',
    warning: 'orange',
    info: 'blue',
  } as const;

  return (
    <Alert
      type={alerts.some((a) => a.status === 'error') ? 'error' : 'warning'}
      showIcon
      icon={<WarningOutlined />}
      message={
        <Space wrap>
          {alerts.map((item) => (
            <Tag key={item.key} color={statusColor[item.status]}>
              {item.title}
            </Tag>
          ))}
        </Space>
      }
      description={
        <Space direction="vertical" size={4}>
          {alerts.map((item) => (
            <Typography.Text key={item.key} type="secondary">
              {item.description}
            </Typography.Text>
          ))}
        </Space>
      }
      style={{ marginBottom: 16 }}
    />
  );
}
