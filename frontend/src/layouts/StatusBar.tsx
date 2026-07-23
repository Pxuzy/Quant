import { useQuery } from '@tanstack/react-query';
import { Space, Typography } from 'antd';
import { apiRequest } from '../shared/api/client';

export function StatusBar() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiRequest('/health'),
    refetchInterval: 30_000,
  });

  return (
    <div className="status-bar">
      <Space size={16}>
        <span className="status-dot" style={{ background: health?.status === 'ok' ? '#22ab94' : '#f23645' }} />
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>{health?.service || 'Quant'} · {health?.environment || '—'}</Typography.Text>
      </Space>
      <Space size={16}>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>股票 5,877</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>日线 107k</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>数据源 AKShare · BaoStock</Typography.Text>
      </Space>
    </div>
  );
}
