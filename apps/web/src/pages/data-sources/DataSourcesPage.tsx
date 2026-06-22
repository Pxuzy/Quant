import { useState, useCallback } from 'react';
import { useDataSourcesQuery, useCheckDataSourceHealthMutation, useSmokeTestDataSourceMutation, useUpdateDataSourceMutation } from '../../features/data-sources/api';
import type { DataSource, DataSourceHealthResult, DataSourceSmokeResult } from '../../features/data-sources/types';
import {
  Button,
  Card,
  Col,
  Divider,
  List,
  message,
  Modal,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExperimentOutlined,
  HeartOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';

const { Text, Paragraph } = Typography;

const STATUS_COLOR: Record<string, string> = {
  healthy: 'green',
  unhealthy: 'red',
  unavailable: 'orange',
  unknown: 'default',
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  healthy: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  unhealthy: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
  unavailable: <WarningOutlined style={{ color: '#faad14' }} />,
};

function CapabilityTag({ label, value }: { label: string; value?: boolean }) {
  return (
    <Tag color={value ? 'blue' : 'default'} style={{ margin: 2 }}>
      {label}: {value ? '✓' : '✗'}
    </Tag>
  );
}

function HealthCheckModal({ source, visible, onClose }: { source: DataSource; visible: boolean; onClose: () => void }) {
  const mutation = useCheckDataSourceHealthMutation();
  const [result, setResult] = useState<DataSourceHealthResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleCheck = useCallback(async () => {
    setLoading(true);
    try {
      const res = await mutation.mutateAsync(source.code);
      setResult(res);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : '检查失败';
      message.error(errMsg);
    } finally {
      setLoading(false);
    }
  }, [source.code, mutation]);

  return (
    <Modal
      title={`健康检查 — ${source.name}`}
      open={visible}
      onCancel={onClose}
      footer={[
        <Button key="check" type="primary" icon={<HeartOutlined />} loading={loading} onClick={handleCheck}>
          开始检查
        </Button>,
        <Button key="close" onClick={onClose}>关闭</Button>,
      ]}
      width={600}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Row gutter={16}>
          <Col span={8}>
            <Statistic title="状态" value={source.health_status} valueStyle={{ color: STATUS_COLOR[source.health_status] }} />
          </Col>
          <Col span={8}>
            <Statistic title="优先级" value={source.priority} />
          </Col>
          <Col span={8}>
            <Statistic title="需要Token" value={source.requires_token ? '是' : '否'} />
          </Col>
        </Row>
        {result && (
          <Card size="small" title="检查结果">
            <Space direction="vertical">
              <Tag color={result.healthy ? 'green' : 'red'}>
                {result.healthy ? '健康' : '异常'} — {result.status}
              </Tag>
              <Text>{result.message}</Text>
            </Space>
          </Card>
        )}
      </Space>
    </Modal>
  );
}

function SmokeTestModal({ source, visible, onClose }: { source: DataSource; visible: boolean; onClose: () => void }) {
  const mutation = useSmokeTestDataSourceMutation();
  const [result, setResult] = useState<DataSourceSmokeResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleTest = useCallback(async () => {
    setLoading(true);
    try {
      const res = await mutation.mutateAsync({ code: source.code });
      setResult(res);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : '测试失败';
      message.error(errMsg);
    } finally {
      setLoading(false);
    }
  }, [source.code, mutation]);

  return (
    <Modal
      title={`实时取样 — ${source.name}`}
      open={visible}
      onCancel={onClose}
      footer={[
        <Button key="test" type="primary" icon={<ExperimentOutlined />} loading={loading} onClick={handleTest}>
          开始取样
        </Button>,
        <Button key="close" onClick={onClose}>关闭</Button>,
      ]}
      width={700}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {result && (
          <>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="能力" value={result.capability} />
              </Col>
              <Col span={6}>
                <Statistic title="原始记录" value={result.raw_records} />
              </Col>
              <Col span={6}>
                <Statistic title="标准化记录" value={result.normalized_records} />
              </Col>
              <Col span={6}>
                <Statistic title="验证错误" value={result.validation_errors.length} valueStyle={{ color: result.validation_errors.length > 0 ? '#ff4d4f' : '#52c41a' }} />
              </Col>
            </Row>
            <Tag color={result.healthy ? 'green' : 'red'}>
              {result.healthy ? '取样成功' : '取样失败'} — {result.status}
            </Tag>
            <Text>{result.message}</Text>
            {result.sample.length > 0 && (
              <Card size="small" title="样本数据 (前3条)">
                <pre style={{ fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
                  {JSON.stringify(result.sample, null, 2)}
                </pre>
              </Card>
            )}
          </>
        )}
      </Space>
    </Modal>
  );
}

export function DataSourcesPage() {
  const { data: sources, isLoading, refetch } = useDataSourcesQuery();
  const updateMutation = useUpdateDataSourceMutation();
  const [healthModal, setHealthModal] = useState<DataSource | null>(null);
  const [smokeModal, setSmokeModal] = useState<DataSource | null>(null);

  const handleToggleEnabled = useCallback(async (source: DataSource) => {
    try {
      await updateMutation.mutateAsync({ code: source.code, payload: { enabled: !source.enabled } });
      message.success(`${source.name} 已${source.enabled ? '禁用' : '启用'}`);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : '操作失败';
      message.error(errMsg);
    }
  }, [updateMutation]);

  const overviewColumns = [
    {
      title: '数据源',
      dataIndex: 'name',
      render: (_: string, r: DataSource) => (
        <Space>
          {STATUS_ICON[r.health_status] || <ApiOutlined />}
          <Text strong>{r.name}</Text>
          <Text type="secondary">({r.code})</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'health_status',
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
    },
    {
      title: '需要Token',
      dataIndex: 'requires_token',
      render: (v: boolean) => <Tag color={v ? 'orange' : 'green'}>{v ? '是' : '否'}</Tag>,
    },
    {
      title: '操作',
      render: (_: unknown, r: DataSource) => (
        <Space>
          <Tooltip title="健康检查">
            <Button size="small" icon={<HeartOutlined />} onClick={() => setHealthModal(r)} />
          </Tooltip>
          <Tooltip title="实时取样">
            <Button size="small" icon={<ExperimentOutlined />} onClick={() => setSmokeModal(r)} />
          </Tooltip>
          <Switch
            size="small"
            checked={r.enabled}
            onChange={() => handleToggleEnabled(r)}
            checkedChildren="启用"
            unCheckedChildren="禁用"
          />
        </Space>
      ),
    },
  ];

  const healthyCount = sources?.filter((s) => s.health_status === 'healthy').length || 0;
  const totalCount = sources?.length || 0;

  const tabItems = [
    {
      key: 'overview',
      label: '数据源总览',
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small">
                <Statistic title="数据源总数" value={totalCount} prefix={<ApiOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="健康" value={healthyCount} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="异常" value={totalCount - healthyCount} prefix={<WarningOutlined />} valueStyle={{ color: '#ff4d4f' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="健康率"
                  value={totalCount > 0 ? Math.round((healthyCount / totalCount) * 100) : 0}
                  suffix="%"
                  prefix={<HeartOutlined />}
                />
              </Card>
            </Col>
          </Row>
          <Card size="small" title="数据源列表" extra={
            <Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>
              刷新
            </Button>
          }>
            <Spin spinning={isLoading}>
              <Table
                dataSource={sources || []}
                columns={overviewColumns}
                rowKey="code"
                size="small"
                pagination={false}
              />
            </Spin>
          </Card>
        </Space>
      ),
    },
    {
      key: 'cards',
      label: '卡片视图',
      children: (
        <Spin spinning={isLoading}>
          <Row gutter={[16, 16]}>
            {(sources || []).map((source) => (
              <Col key={source.code} xs={24} sm={12} lg={8}>
                <Card
                  size="small"
                  title={
                    <Space>
                      {STATUS_ICON[source.health_status] || <ApiOutlined />}
                      <Text strong>{source.name}</Text>
                    </Space>
                  }
                  extra={
                    <Switch
                      size="small"
                      checked={source.enabled}
                      onChange={() => handleToggleEnabled(source)}
                    />
                  }
                  hoverable
                >
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Row gutter={8}>
                      <Col span={12}>
                        <Statistic title="状态" value={source.health_status} valueStyle={{ fontSize: 14, color: STATUS_COLOR[source.health_status] }} />
                      </Col>
                      <Col span={12}>
                        <Statistic title="优先级" value={source.priority} valueStyle={{ fontSize: 14 }} />
                      </Col>
                    </Row>
                    <div>
                      <Text type="secondary">能力: </Text>
                      {(source.capabilities?.stock_list || (source.config_json as Record<string, unknown>)?.capabilities === 'object' && ((source.config_json as Record<string, unknown>)?.capabilities as Record<string, boolean>)?.stock_list) && <Tag color="blue" size="small">股票列表</Tag>}
                      {(source.capabilities?.daily_bars || ((source.config_json as Record<string, unknown>)?.capabilities as Record<string, boolean>)?.daily_bars) && <Tag color="green" size="small">日K线</Tag>}
                      {(source.capabilities?.calendars || ((source.config_json as Record<string, unknown>)?.capabilities as Record<string, boolean>)?.calendars) && <Tag color="orange" size="small">日历</Tag>}
                    </div>
                    {source.last_checked_at && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        最后检查: {source.last_checked_at}
                      </Text>
                    )}
                    <Space>
                      <Button size="small" icon={<HeartOutlined />} onClick={() => setHealthModal(source)}>健康检查</Button>
                      <Button size="small" icon={<ExperimentOutlined />} onClick={() => setSmokeModal(source)}>取样</Button>
                    </Space>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        </Spin>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Typography.Title level={4} style={{ margin: 0 }}>
            数据源管理
          </Typography.Title>
        </Col>
        <Col>
          <Button type="primary" icon={<ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>
            刷新全部
          </Button>
        </Col>
      </Row>

      <Tabs defaultActiveKey="overview" items={tabItems} />

      {healthModal && (
        <HealthCheckModal source={healthModal} visible={!!healthModal} onClose={() => setHealthModal(null)} />
      )}
      {smokeModal && (
        <SmokeTestModal source={smokeModal} visible={!!smokeModal} onClose={() => setSmokeModal(null)} />
      )}
    </Space>
  );
}
