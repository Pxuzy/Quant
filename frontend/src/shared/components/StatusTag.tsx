import { Tag } from 'antd';

const STATUS_META: Record<string, { color: string; label: string }> = {
  LISTED: { color: 'success', label: '上市' },
  SUSPENDED: { color: 'warning', label: '停牌' },
  DELISTED: { color: 'default', label: '退市' },
  pending: { color: 'processing', label: '等待中' },
  running: { color: 'blue', label: '运行中' },
  success: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  canceled: { color: 'default', label: '已取消' },
  healthy: { color: 'success', label: '健康' },
  unhealthy: { color: 'error', label: '异常' },
  unavailable: { color: 'warning', label: '不可用' },
  good: { color: 'success', label: '通过' },
  warning: { color: 'warning', label: '警告' },
  error: { color: 'error', label: '错误' },
  unknown: { color: 'default', label: '未知' },
};

type StatusTagProps = {
  value?: string | null;
};

export function StatusTag({ value }: StatusTagProps) {
  if (!value) {
    return <Tag>未知</Tag>;
  }

  const meta = STATUS_META[value] ?? { color: 'default', label: value };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}
