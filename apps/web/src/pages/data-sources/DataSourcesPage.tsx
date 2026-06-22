import { useState, useCallback, type ReactNode } from 'react';
import { useDataSourcesQuery, useCheckDataSourceHealthMutation, useSmokeTestDataSourceMutation, useUpdateDataSourceMutation } from '../../features/data-sources/api';
import type { DataSource, DataSourceHealthResult, DataSourceSmokeResult } from '../../features/data-sources/types';
import * as Icons from '@ant-design/icons';
import { Button, Card, Col, message, Modal, Row, Space, Spin, Statistic, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd';

const { Text } = Typography;

// ponytail: 合并 STATUS_COLOR 和 STATUS_ICON 为单一映射
const STATUS: Record<string, { color: string; icon: ReactNode }> = {
  healthy: { color: 'green', icon: <Icons.CheckCircleOutlined style={{ color: '#52c41a' }} /> },
  unhealthy: { color: 'red', icon: <Icons.CloseCircleOutlined style={{ color: '#ff4d4f' }} /> },
  unavailable: { color: 'orange', icon: <Icons.WarningOutlined style={{ color: '#faad14' }} /> },
};

// ponytail: 合并两个 Modal 为一个通用结果 Modal
function ResultModal({ title, visible, onClose, onAction, actionIcon, actionText, mutationFn, source, renderResult }: {
  title: string; visible: boolean; onClose: () => void;
  onAction: () => void; actionIcon: ReactNode; actionText: string;
  mutationFn: (code: string) => Promise<DataSourceHealthResult | DataSourceSmokeResult>;
  source: DataSource;
  renderResult: (r: DataSourceHealthResult | DataSourceSmokeResult) => ReactNode;
}) {
  const [result, setResult] = useState<DataSourceHealthResult | DataSourceSmokeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const handle = useCallback(async () => {
    setLoading(true);
    try { setResult(await mutationFn(source.code)); }
    catch (e: unknown) { message.error(e instanceof Error ? e.message : '操作失败'); }
    finally { setLoading(false); }
  }, [source.code, mutationFn]);

  return (
    <Modal title={`${title} — ${source.name}`} open={visible} onCancel={onClose}
      footer={[<Button key="action" type="primary" icon={actionIcon} loading={loading} onClick={handle}>{actionText}</Button>, <Button key="close" onClick={onClose}>关闭</Button>]}>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {result && renderResult(result)}
      </Space>
    </Modal>
  );
}

export function DataSourcesPage() {
  const { data: sources, isLoading, refetch } = useDataSourcesQuery();
  const updateMutation = useUpdateDataSourceMutation();
  const [healthModal, setHealthModal] = useState<DataSource | null>(null);
  const [smokeModal, setSmokeModal] = useState<DataSource | null>(null);

  const handleToggle = useCallback(async (s: DataSource) => {
    try {
      await updateMutation.mutateAsync({ code: s.code, payload: { enabled: !s.enabled } });
      message.success(`${s.name} 已${s.enabled ? '禁用' : '启用'}`);
    } catch (e: unknown) { message.error(e instanceof Error ? e.message : '操作失败'); }
  }, [updateMutation]);

  const StatusIcon = ({ status }: { status: string }) => <>{(STATUS[status] || { icon: <Icons.ApiOutlined /> }).icon}</>;

  const overviewColumns = [
    { title: '数据源', dataIndex: 'name', render: (_: string, r: DataSource) => (
      <Space><StatusIcon status={r.health_status} /><Text strong>{r.name}</Text><Text type="secondary">({r.code})</Text></Space>
    )},
    { title: '状态', dataIndex: 'health_status', render: (s: string) => <Tag color={STATUS[s]?.color || 'default'}>{s}</Tag> },
    { title: '优先级', dataIndex: 'priority' },
    { title: '需Token', dataIndex: 'requires_token', render: (v: boolean) => <Tag color={v ? 'orange' : 'green'}>{v ? '是' : '否'}</Tag> },
    { title: '操作', render: (_: unknown, r: DataSource) => (
      <Space>
        <Tooltip title="健康检查"><Button size="small" icon={<Icons.HeartOutlined />} onClick={() => setHealthModal(r)} /></Tooltip>
        <Tooltip title="实时取样"><Button size="small" icon={<Icons.ExperimentOutlined />} onClick={() => setSmokeModal(r)} /></Tooltip>
        <Switch size="small" checked={r.enabled} onChange={() => handleToggle(r)} />
      </Space>
    )},
  ];

  const healthyCount = sources?.filter((s) => s.health_status === 'healthy').length || 0;
  const totalCount = sources?.length || 0;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      <Row justify="space-between" align="middle">
        <Col><Typography.Title level={4} style={{ margin: 0 }}>数据源管理</Typography.Title></Col>
        <Col><Button type="primary" icon={<Icons.ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>刷新</Button></Col>
      </Row>

      <Tabs defaultActiveKey="overview" items={[
        { key: 'overview', label: '数据源总览', children: (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Row gutter={16}>
              {[
                ['总数', totalCount, <Icons.ApiOutlined />],
                ['健康', healthyCount, <Icons.CheckCircleOutlined />, '#52c41a'],
                ['异常', totalCount - healthyCount, <Icons.WarningOutlined />, '#ff4d4f'],
                ['健康率', `${totalCount > 0 ? Math.round((healthyCount / totalCount) * 100) : 0}%`, <Icons.HeartOutlined />],
              ].map(([label, value, icon, color]) => (
                <Col span={6} key={label as string}><Card size="small"><Statistic title={label as string} value={value as ReactNode} prefix={icon as ReactNode} valueStyle={color ? { color } : undefined} /></Card></Col>
              ))}
            </Row>
            <Card size="small" title="数据源列表" extra={<Button size="small" icon={<Icons.ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>刷新</Button>}>
              <Spin spinning={isLoading}><Table dataSource={sources || []} columns={overviewColumns} rowKey="code" size="small" pagination={false} /></Spin>
            </Card>
          </Space>
        )},
        { key: 'cards', label: '卡片视图', children: (
          <Spin spinning={isLoading}>
            <Row gutter={[16, 16]}>
              {(sources || []).map((s) => {
                const caps = (s.capabilities || s.config_json?.capabilities || {}) as Record<string, boolean>;
                return (
                  <Col key={s.code} xs={24} sm={12} lg={8}>
                    <Card size="small" title={<Space><StatusIcon status={s.health_status} /><Text strong>{s.name}</Text></Space>}
                      extra={<Switch size="small" checked={s.enabled} onChange={() => handleToggle(s)} />} hoverable>
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Row gutter={8}>
                          <Col span={12}><Statistic title="状态" value={s.health_status} valueStyle={{ fontSize: 14, color: STATUS[s.health_status]?.color }} /></Col>
                          <Col span={12}><Statistic title="优先级" value={s.priority} valueStyle={{ fontSize: 14 }} /></Col>
                        </Row>
                        <div><Text type="secondary">能力: </Text>
                          {caps.stock_list && <Tag color="blue" size="small">股票列表</Tag>}
                          {caps.daily_bars && <Tag color="green" size="small">日K线</Tag>}
                          {caps.calendars && <Tag color="orange" size="small">日历</Tag>}
                        </div>
                        {s.last_checked_at && <Text type="secondary" style={{ fontSize: 12 }}>最后检查: {s.last_checked_at}</Text>}
                        <Space>
                          <Button size="small" icon={<Icons.HeartOutlined />} onClick={() => setHealthModal(s)}>健康检查</Button>
                          <Button size="small" icon={<Icons.ExperimentOutlined />} onClick={() => setSmokeModal(s)}>取样</Button>
                        </Space>
                      </Space>
                    </Card>
                  </Col>
                );
              })}
            </Row>
          </Spin>
        )},
      ]} />

      {healthModal && <ResultModal title="健康检查" visible={!!healthModal} onClose={() => setHealthModal(null)}
        onAction={() => {}} actionIcon={<Icons.HeartOutlined />} actionText="开始检查"
        mutationFn={useCheckDataSourceHealthMutation().mutateAsync} source={healthModal}
        renderResult={(r) => {
          const res = r as DataSourceHealthResult;
          return <Space direction="vertical"><Tag color={res.healthy ? 'green' : 'red'}>{res.healthy ? '健康' : '异常'} — {res.status}</Tag><Text>{res.message}</Text></Space>;
        }} />}

      {smokeModal && <ResultModal title="实时取样" visible={!!smokeModal} onClose={() => setSmokeModal(null)}
        onAction={() => {}} actionIcon={<Icons.ExperimentOutlined />} actionText="开始取样"
        mutationFn={useSmokeTestDataSourceMutation().mutateAsync} source={smokeModal}
        renderResult={(r) => {
          const res = r as DataSourceSmokeResult;
          return <Space direction="vertical">
            <Row gutter={16}>
              <Col span={6}><Statistic title="能力" value={res.capability} /></Col>
              <Col span={6}><Statistic title="原始记录" value={res.raw_records} /></Col>
              <Col span={6}><Statistic title="标准化" value={res.normalized_records} /></Col>
              <Col span={6}><Statistic title="错误" value={res.validation_errors.length} /></Col>
            </Row>
            <Tag color={res.healthy ? 'green' : 'red'}>{res.healthy ? '成功' : '失败'} — {res.status}</Tag>
            <Text>{res.message}</Text>
            {res.sample.length > 0 && <Card size="small" title="样本"><pre style={{ fontSize: 12, maxHeight: 200, overflow: 'auto' }}>{JSON.stringify(res.sample, null, 2)}</pre></Card>}
          </Space>;
        }} />}
    </Space>
  );
}
