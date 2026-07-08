import { Button, Space, Tooltip } from 'antd';
import { BarChartOutlined, CloudSyncOutlined, ReloadOutlined } from '@ant-design/icons';

export function QuickActions({
  onRefresh,
  onSyncStocks,
  syncLoading,
  onOpenNumericSummary,
  onOpenStocks,
}: {
  onRefresh: () => void;
  onSyncStocks: () => void;
  syncLoading?: boolean;
  onOpenNumericSummary: () => void;
  onOpenStocks: () => void;
}) {
  return (
    <Space wrap size={8}>
      <Tooltip title="刷新总控台数据">
        <Button icon={<ReloadOutlined />} onClick={onRefresh} />
      </Tooltip>
      <Button type="primary" icon={<CloudSyncOutlined />} loading={syncLoading} onClick={onSyncStocks}>
        更新股票池
      </Button>
      <Button icon={<BarChartOutlined />} onClick={onOpenNumericSummary}>
        数值汇总
      </Button>
      <Button onClick={onOpenStocks}>
        股票池
      </Button>
    </Space>
  );
}
