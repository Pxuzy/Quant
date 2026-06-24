import { useMemo, useState } from 'react';
import {
  ApiOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  App as AntApp,
  Alert,
  Button,
  Card,
  Col,
  Input,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQueryClient } from '@tanstack/react-query';
import {
  useCheckDataSourceHealthMutation,
  useDataSourceCatalogQuery,
  useDataSourcesQuery,
  useSmokeTestDataSourceMutation,
  useUpdateDataSourceMutation,
} from '../../../features/data-sources/api';
import type { DataSource, DataSourceCatalogItem } from '../../../features/data-sources/types';
import { useSyncStocksMutation } from '../../../features/stocks/api';
import { formatCapability, formatExchange, formatProviderType } from '../../../shared/domain/labels';
import { AuthStatusTag, resolveAuthStatus } from '../../../shared/components/AuthStatusTag';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatDateTime, formatNumber } from '../../../shared/components/formatters';

const STATUS_COLOR: Record<string, string> = {
  healthy: 'green',
  unhealthy: 'red',
  unavailable: 'orange',
  unknown: 'default',
};

const CATALOG_KIND_LABELS: Record<string, string> = {
  community_mcp: '开源 MCP',
};

const CATALOG_STATUS_LABELS: Record<string, string> = {
  registered_adapter: '已接入',
  candidate: '候选',
  requires_license: '需授权',
  research_only: '研究用',
};

const CATALOG_CAPABILITY_LABELS: Record<string, string> = {
  sector_data: '板块数据',
  concept_board: '概念板块',
  market_data: '行情',
  ai_agent_tools: 'Agent 工具',
  public_data_wrappers: '公开数据封装',
  tushare_api_wrapper: 'Tushare 封装',
  akshare_public_data: 'AKShare 公开数据',
  a_share_data: 'A 股数据',
  financial_reports: '财报',
  industry_data: '行业数据',
  macro_data: '宏观数据',
};

function formatCatalogValue(value: string, labels: Record<string, string>) {
  return labels[value] ?? value;
}

function getCapabilities(s: DataSource) {
  const cap = (s.config_json?.capabilities || {}) as Record<string, unknown>;
  return cap;
}

function smokeCaps(s: DataSource) {
  const cap = getCapabilities(s);
  return Object.entries(cap)
    .filter(([k, v]) => Boolean(v) && (k === 'stock_list' || k === 'daily_bars' || k === 'intraday' || k === 'news' || k === 'fundamentals'))
    .map(([k]) => k);
}

export function DataSourcesPage() {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const query = useDataSourcesQuery();
  const catalogQuery = useDataSourceCatalogQuery();
  const updateMutation = useUpdateDataSourceMutation();
  const healthMutation = useCheckDataSourceHealthMutation();
  const smokeMutation = useSmokeTestDataSourceMutation();
  const syncMutation = useSyncStocksMutation();

  const [keyword, setKeyword] = useState('');

  const sources = useMemo(() => query.data ?? [], [query.data]);
  const catalog = useMemo(() => catalogQuery.data ?? [], [catalogQuery.data]);
  const filtered = useMemo(() => {
    const k = keyword.trim().toLowerCase();
    if (!k) return sources;
    return sources.filter(
      (s) =>
        s.name.toLowerCase().includes(k) ||
        s.code.toLowerCase().includes(k) ||
        (s.health_status || '').toLowerCase().includes(k),
    );
  }, [sources, keyword]);
  const filteredCatalog = useMemo(() => {
    const k = keyword.trim().toLowerCase();
    if (!k) return catalog;
    return catalog.filter(
      (item) =>
        item.name.toLowerCase().includes(k) ||
        item.code.toLowerCase().includes(k) ||
        item.source_kind.toLowerCase().includes(k) ||
        item.integration_status.toLowerCase().includes(k) ||
        item.capabilities.some((capability) => capability.toLowerCase().includes(k)),
    );
  }, [catalog, keyword]);

  const summary = useMemo(() => {
    const healthy = sources.filter((s) => s.health_status === 'healthy').length;
    const unhealthy = sources.filter((s) => s.health_status === 'unhealthy').length;
    const unavailable = sources.filter((s) => s.health_status === 'unavailable').length;
    const unknown = sources.filter((s) => !s.health_status || s.health_status === 'unknown').length;
    return { healthy, unhealthy, unavailable, unknown, total: sources.length };
  }, [sources]);

  const refresh = () => {
    void query.refetch();
    void catalogQuery.refetch();
    void queryClient.invalidateQueries({ queryKey: ['data', 'data-sources'] });
  };

  const columns: ColumnsType<DataSource> = [
    {
      title: '数据源',
      dataIndex: 'name',
      fixed: 'left',
      width: 220,
      sorter: (a, b) => a.name.localeCompare(b.name, 'zh-CN'),
      render: (_, r) => (
        <Space size={6}>
          <ApiOutlined style={{ color: '#1677ff' }} />
          <Typography.Text strong>{r.name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>({r.code})</Typography.Text>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: ['config_json', 'provider_metadata', 'provider_type'],
      width: 110,
      render: (v) => (v ? <Tag color="blue">{formatProviderType(String(v))}</Tag> : <Tag>未知</Tag>),
    },
    {
      title: '交易所',
      width: 110,
      render: (_, r) => {
        const ex = (r.config_json?.capabilities as Record<string, unknown> | undefined)?.daily_bar_exchanges as string[] | undefined;
        if (!ex || !ex.length) return <Tag>—</Tag>;
        return (
          <Space size={2} wrap>
            {ex.slice(0, 2).map((e) => (
              <Tag key={e} color="geekblue">{formatExchange(e)}</Tag>
            ))}
            {ex.length > 2 && <Tag>+{ex.length - 2}</Tag>}
          </Space>
        );
      },
    },
    {
      title: '认证',
      dataIndex: 'requires_token',
      width: 100,
      render: (req, r) => (
        <AuthStatusTag
          status={resolveAuthStatus({
            authStatus: r.auth_status,
            configAuthStatus: r.config_json?.auth_status as string | undefined,
            requiresToken: Boolean(r.requires_token),
          })}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'health_status',
      width: 110,
      sorter: (a, b) => (a.health_status || '').localeCompare(b.health_status || ''),
      render: (s) => <StatusTag value={s || 'unknown'} />,
    },
    {
      title: '能力',
      width: 200,
      render: (_, r) => {
        const caps = smokeCaps(r);
        if (!caps.length) return <Typography.Text type="secondary">—</Typography.Text>;
        return (
          <Space size={2} wrap>
            {caps.slice(0, 3).map((c) => (
              <Tag key={c} color="default">{formatCapability(c)}</Tag>
            ))}
            {caps.length > 3 && <Tag>+{caps.length - 3}</Tag>}
          </Space>
        );
      },
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      sorter: (a, b) => (a.priority ?? 0) - (b.priority ?? 0),
      defaultSortOrder: 'ascend',
      render: (v) => <Typography.Text strong>{v ?? '—'}</Typography.Text>,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      filters: [
        { text: '已启用', value: true },
        { text: '已禁用', value: false },
      ],
      onFilter: (v, r) => Boolean(r.enabled) === Boolean(v),
      render: (v, r) => (
        <Switch
          size="small"
          checked={Boolean(v)}
          loading={
            updateMutation.isPending &&
            updateMutation.variables?.code === r.code &&
            'enabled' in (updateMutation.variables?.payload || {})
          }
          onChange={(checked) =>
            updateMutation.mutate(
              { code: r.code, payload: { enabled: checked } },
              {
                onSuccess: () => void message.success(`${r.name} 已${checked ? '启用' : '禁用'}`),
                onError: (e) => void message.error(e instanceof Error ? e.message : '更新失败'),
              },
            )
          }
        />
      ),
    },
    {
      title: '最后检查',
      dataIndex: 'last_checked_at',
      width: 160,
      render: (v) => v ? <Typography.Text style={{ fontSize: 12 }}>{formatDateTime(String(v))}</Typography.Text> : <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right',
      render: (_, r) => {
        const caps = smokeCaps(r);
        const isHealthRunning =
          healthMutation.isPending && healthMutation.variables === r.code;
        const isSmokeRunning =
          smokeMutation.isPending && smokeMutation.variables?.code === r.code;
        const isSyncRunning =
          syncMutation.isPending &&
          syncMutation.variables &&
          (syncMutation.variables as { source?: string }).source === r.code;
        return (
          <Space size={4} wrap>
            <Tooltip title="健康检查">
              <Button
                size="small"
                icon={<CheckCircleOutlined />}
                loading={isHealthRunning}
                onClick={() =>
                  healthMutation.mutate(r.code, {
                    onSuccess: (res) => void message[res.healthy ? 'success' : 'warning'](res.message),
                    onError: (e) => void message.error(e instanceof Error ? e.message : '检查失败'),
                  })
                }
              />
            </Tooltip>
            <Tooltip title={caps.length ? `取样 (${caps.length} 项)` : '无可取样能力'}>
              <Popconfirm
                title="真实取样"
                description="下一步将调用上游取最近日线样本。"
                okText="开始"
                cancelText="取消"
                disabled={!caps.length}
                onConfirm={() =>
                  smokeMutation.mutate(
                    { code: r.code, capability: 'daily_bars' as never },
                    {
                      onSuccess: (res) =>
                        void message[res.healthy ? 'success' : 'warning'](
                          `${formatCapability(res.capability)}：原始 ${formatNumber(res.raw_records)} / 归一 ${formatNumber(res.normalized_records)}`,
                        ),
                      onError: (e) => void message.error(e instanceof Error ? e.message : '取样失败'),
                    },
                  )
                }
              >
                <Button
                  size="small"
                  icon={<ExperimentOutlined />}
                  loading={isSmokeRunning}
                  disabled={!caps.length}
                />
              </Popconfirm>
            </Tooltip>
            <Tooltip title="同步股票池">
              <Button
                size="small"
                icon={<PlayCircleOutlined />}
                loading={isSyncRunning}
                disabled={!r.enabled}
                onClick={() =>
                  syncMutation.mutate(
                    { source: r.code, market: 'A_SHARE' },
                    {
                      onSuccess: () => void message.success(`${r.name} 同步任务已创建`),
                      onError: (e) => void message.error(e instanceof Error ? e.message : '同步任务创建失败'),
                    },
                  )
                }
              />
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  const catalogColumns: ColumnsType<DataSourceCatalogItem> = [
    {
      title: '候选服务',
      dataIndex: 'name',
      width: 220,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Space size={6}>
            <SafetyCertificateOutlined style={{ color: item.authorization_required ? '#faad14' : '#52c41a' }} />
            <Typography.Text strong>{item.name}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>({item.code})</Typography.Text>
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {item.recommended_use}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '类别',
      dataIndex: 'source_kind',
      width: 110,
      render: (value) => <Tag color="blue">{formatCatalogValue(String(value), CATALOG_KIND_LABELS)}</Tag>,
    },
    {
      title: '接入状态',
      dataIndex: 'integration_status',
      width: 100,
      render: (value) => {
        const text = String(value);
        const color = text === 'registered_adapter' ? 'green' : text === 'requires_license' ? 'orange' : 'default';
        return <Tag color={color}>{formatCatalogValue(text, CATALOG_STATUS_LABELS)}</Tag>;
      },
    },
    {
      title: 'MCP 定位',
      dataIndex: 'mcp_role',
      width: 100,
      render: (value) => (value ? <Tag color="purple">适配层</Tag> : <Typography.Text type="secondary">—</Typography.Text>),
    },
    {
      title: '授权',
      dataIndex: 'authorization_required',
      width: 90,
      render: (value) => <Tag color={value ? 'orange' : 'green'}>{value ? '需确认' : '公开/免凭证'}</Tag>,
    },
    {
      title: '板块能力',
      dataIndex: 'capabilities',
      width: 220,
      render: (capabilities: string[]) => (
        <Space size={2} wrap>
          {capabilities.slice(0, 4).map((capability) => (
            <Tag key={capability}>{formatCatalogValue(capability, CATALOG_CAPABILITY_LABELS)}</Tag>
          ))}
          {capabilities.length > 4 && <Tag>+{capabilities.length - 4}</Tag>}
        </Space>
      ),
    },
    {
      title: '边界',
      dataIndex: 'production_note',
      width: 280,
      render: (value) => <Typography.Text type="secondary" style={{ fontSize: 12 }}>{value}</Typography.Text>,
    },
    {
      title: '链接',
      width: 140,
      render: (_, item) => (
        <Space size={6} wrap>
          {item.docs_url && (
            <Typography.Link href={item.docs_url} target="_blank" rel="noreferrer">文档</Typography.Link>
          )}
          {item.mcp_url && (
            <Typography.Link href={item.mcp_url} target="_blank" rel="noreferrer">MCP</Typography.Link>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="workbench data-sources-page" style={{ padding: '12px 16px' }}>
      <Space direction="vertical" size={4} style={{ marginBottom: 12 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>数据源管理</Typography.Title>
        <Typography.Text type="secondary">
          接入目录 · 依赖检查 · 真实取样 · 同步入口 &nbsp;|&nbsp; 跨数据集告警请到
          <Typography.Link href="/data-system/alerts" style={{ marginLeft: 4 }}>异常中心</Typography.Link>
        </Typography.Text>
      </Space>

      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col xs={12} md={6}>
          <Card size="small"><Statistic title="注册来源" value={summary.total} suffix="个" prefix={<ApiOutlined />} loading={query.isLoading} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Statistic title="健康" value={summary.healthy} suffix="个" prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} loading={query.isLoading} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Statistic title="异常 / 不可用" value={summary.unhealthy + summary.unavailable} suffix="个" prefix={<WarningOutlined />} valueStyle={{ color: summary.unhealthy + summary.unavailable > 0 ? '#ff4d4f' : undefined }} loading={query.isLoading} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small"><Statistic title="未检查" value={summary.unknown} suffix="个" prefix={<SyncOutlined />} loading={query.isLoading} /></Card>
        </Col>
      </Row>

      {query.isError && (
        <Alert type="error" showIcon style={{ marginBottom: 12 }} message="数据源加载失败" description="后端数据源管理接口暂不可用，请稍后再试。" />
      )}

      <Card
        size="small"
        title={
          <Space>
            <ApiOutlined />
            <span>数据源列表</span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>共 {sources.length} 个{keyword && ` · 过滤后 ${filtered.length}`}</Typography.Text>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索 名称 / code / 状态"
              allowClear
              onSearch={setKeyword}
              onChange={(e) => !e.target.value && setKeyword('')}
              style={{ width: 220 }}
            />
            <Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={refresh}>刷新</Button>
          </Space>
        }
        bodyStyle={{ padding: 0 }}
      >
        <Table<DataSource>
          rowKey="code"
          size="small"
          dataSource={filtered}
          columns={columns}
          pagination={{
            pageSize: 10,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
          }}
          scroll={{ x: 1200 }}
          loading={query.isLoading}
          rowClassName={(r) =>
            r.health_status === 'unhealthy' ? 'row-unhealthy'
              : r.health_status === 'unavailable' ? 'row-unavailable'
              : ''
          }
        />
      </Card>

      <Card
        size="small"
        style={{ marginTop: 12 }}
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>免费 MCP 候选目录</span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              共 {catalog.length} 个{keyword && ` · 过滤后 ${filteredCatalog.length}`}
            </Typography.Text>
          </Space>
        }
        bodyStyle={{ padding: 0 }}
      >
        <Table<DataSourceCatalogItem>
          rowKey="code"
          size="small"
          dataSource={filteredCatalog}
          columns={catalogColumns}
          pagination={{
            pageSize: 6,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
          }}
          scroll={{ x: 1280 }}
          loading={catalogQuery.isLoading}
        />
      </Card>
    </div>
  );
}
