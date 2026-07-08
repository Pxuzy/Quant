import { useQuery } from '@tanstack/react-query';
import * as Icons from '@ant-design/icons';
import { Button, Card, Col, Row, Space, Spin, Statistic, Table, Tag, Typography } from 'antd';
import { apiRequest } from '../../../shared/api/client';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import type { DataSource } from '../../../features/data-sources/types';

const STATUS_COLOR: Record<string, string> = { healthy: 'green', unhealthy: 'red', unavailable: 'orange' };

export function AlertsPage() {
  const { data: sources, isLoading, refetch } = useDataSourcesQuery();

  const unhealthy = (sources || []).filter((s) => s.health_status !== 'healthy');
  const healthy = (sources || []).filter((s) => s.health_status === 'healthy');

  const columns = [
    { title: '数据源', dataIndex: 'name', render: (_: string, r: DataSource) => (
      <Space><Icons.ApiOutlined /><Typography.Text strong>{r.name}</Typography.Text><Typography.Text type="secondary">({r.code})</Typography.Text></Space>
    )},
    { title: '状态', dataIndex: 'health_status', render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag> },
    { title: '优先级', dataIndex: 'priority' },
    { title: '启用', dataIndex: 'enabled', render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '是' : '否'}</Tag> },
    { title: '需Token', dataIndex: 'requires_token', render: (v: boolean) => <Tag color={v ? 'orange' : 'green'}>{v ? '是' : '否'}</Tag> },
    { title: '最后检查', dataIndex: 'last_checked_at', render: (v: string | null) => v || '-' },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      <Row justify="space-between" align="middle">
        <Col><Typography.Title level={4} style={{ margin: 0 }}>异常中心</Typography.Title></Col>
        <Col><Button type="primary" icon={<Icons.ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>刷新</Button></Col>
      </Row>

      <Spin spinning={isLoading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {[
            ['数据源总数', sources?.length || 0, <Icons.ApiOutlined />],
            ['健康', healthy.length, <Icons.CheckCircleOutlined />, '#52c41a'],
            ['异常', unhealthy.length, <Icons.WarningOutlined />, unhealthy.length > 0 ? '#ff4d4f' : '#52c41a'],
          ].map(([label, value, icon, color]) => (
            <Col span={8} key={label as string}>
              <Card size="small">
                <Statistic title={label as string} value={value as number} prefix={icon as React.ReactNode}
                  valueStyle={color ? { color: color as string } : undefined} />
              </Card>
            </Col>
          ))}
        </Row>

        {unhealthy.length > 0 && (
          <Card size="small" title="⚠️ 异常数据源" style={{ marginBottom: 16 }}>
            <Table dataSource={unhealthy} columns={columns} rowKey="code" size="small" pagination={false} />
          </Card>
        )}

        <Card size="small" title="所有数据源状态">
          <Table dataSource={sources || []} columns={columns} rowKey="code" size="small" pagination={false} />
        </Card>
      </Spin>
    </Space>
  );
}
