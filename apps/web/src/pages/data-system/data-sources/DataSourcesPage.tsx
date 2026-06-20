import { useMemo, useRef } from 'react';
import {
  ApiOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  App as AntApp,
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  InputNumber,
  Row,
  Space,
  Statistic,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  useCheckDataSourceHealthMutation,
  useDataSourcesQuery,
  useSmokeTestDataSourceMutation,
  useUpdateDataSourceMutation,
} from '../../../features/data-sources/api';
import type { DataSource } from '../../../features/data-sources/types';
import { useSyncStocksMutation } from '../../../features/stocks/api';
import { AuthStatusTag, resolveAuthStatus } from '../../../shared/components/AuthStatusTag';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatDateTime, formatNumber } from '../../../shared/components/formatters';
import {
  formatAuthMode,
  formatCapability,
  formatExchange,
  formatProviderType,
  formatStability,
} from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

const V1_DATA_SOURCE_CODES = new Set(['akshare', 'baostock', 'adata', 'tushare', 'stock_sdk']);
const DATA_SOURCE_HEALTH_RANK: Record<string, number> = {
  healthy: 0,
  unhealthy: 1,
  unavailable: 2,
  unknown: 3,
};

const fallbackDataSources: DataSource[] = [
  {
    id: 'fallback-akshare',
    code: 'akshare',
    name: 'AKShare',
    enabled: true,
    priority: 10,
    requires_token: false,
    health_status: 'unknown',
    config_json: {
      capabilities: { stock_list: true, daily_bars: true, daily_bar_exchanges: ['SSE', 'SZSE', 'BSE'] },
      provider_metadata: {
        provider_type: 'python_package',
        auth_mode: 'none',
        stability: 'community',
        install_note: 'pip install akshare',
        rate_limit_note: '公共接口，速度和稳定性取决于上游。',
      },
    },
  },
  {
    id: 'fallback-baostock',
    code: 'baostock',
    name: 'BaoStock',
    enabled: true,
    priority: 20,
    requires_token: false,
    health_status: 'unknown',
    config_json: {
      capabilities: { stock_list: true, daily_bars: true, calendars: true, daily_bar_exchanges: ['SSE', 'SZSE'] },
      provider_metadata: {
        provider_type: 'python_package',
        auth_mode: 'none',
        stability: 'community',
        install_note: 'pip install baostock',
        rate_limit_note: '需要登录会话，适合股票池、日线和交易日历补充。',
      },
    },
  },
  {
    id: 'fallback-adata',
    code: 'adata',
    name: 'adata',
    enabled: true,
    priority: 30,
    requires_token: false,
    health_status: 'unknown',
    config_json: {
      capabilities: { stock_list: true, daily_bars: true, daily_bar_exchanges: ['SSE', 'SZSE'] },
      provider_metadata: {
        provider_type: 'python_package',
        auth_mode: 'none',
        stability: 'community',
        install_note: 'pip install adata',
        rate_limit_note: '社区数据源，建议先真实取样再用于批量同步。',
      },
    },
  },
  {
    id: 'fallback-tushare',
    code: 'tushare',
    name: 'TuShare',
    enabled: false,
    priority: 40,
    requires_token: true,
    auth_status: 'missing',
    health_status: 'unavailable',
    config_json: {
      capabilities: { stock_list: true, daily_bars: true, calendars: true, daily_bar_exchanges: ['SSE', 'SZSE'] },
      auth_status: 'missing',
      provider_metadata: {
        provider_type: 'external_api',
        auth_mode: 'token',
        stability: 'official',
        install_note: 'pip install tushare，并配置 token。',
        rate_limit_note: '受账号积分和接口频率限制。',
      },
    },
  },
  {
    id: 'fallback-stock-sdk',
    code: 'stock_sdk',
    name: 'stock-sdk',
    enabled: true,
    priority: 50,
    requires_token: false,
    health_status: 'unknown',
    config_json: {
      capabilities: { stock_list: true, daily_bars: true, daily_bar_exchanges: ['SSE', 'SZSE'] },
      provider_metadata: {
        provider_type: 'python_package',
        auth_mode: 'none',
        stability: 'community',
        install_note: '安装 chengzuopeng/stock-sdk 对应 Python 包或本地适配模块。',
        rate_limit_note: '第三方社区库，建议作为补充来源使用。',
      },
    },
  },
];

function smokeCapabilityOptions(source: DataSource) {
  const capabilities = getCapabilities(source);
  return [
    capabilities.stock_list ? { key: 'stock_list', label: '股票池取样' } : null,
    capabilities.daily_bars ? { key: 'daily_bars', label: '日线取样' } : null,
    capabilities.calendars ? { key: 'calendars', label: '交易日历取样' } : null,
  ].filter((item): item is { key: string; label: string } => Boolean(item));
}

function getCapabilities(source: DataSource) {
  return source.capabilities ?? source.config_json?.capabilities ?? {};
}

function getMetadata(source: DataSource) {
  return source.provider_metadata ?? source.config_json?.provider_metadata ?? {};
}

function explainSourceStatus(source: DataSource) {
  if (source.health_status === 'unknown') {
    return '尚未检查';
  }
  if (source.health_status === 'unavailable') {
    if (source.auth_status === 'missing' || source.config_json?.auth_status === 'missing') {
      return '缺少凭证';
    }
    return '依赖或上游未就绪';
  }
  if (source.health_status === 'unhealthy') {
    return '最近检查未通过';
  }
  return '正常';
}

function explainSourceAction(source: DataSource) {
  if (!source.enabled) {
    return '先启用后再做取样或同步。';
  }
  if (source.health_status === 'healthy') {
    return '可直接取样或同步。';
  }
  if (source.health_status === 'unavailable') {
    return '先补依赖或凭证，再继续。';
  }
  return '先健康检查，再决定是否启用。';
}

function tokenStatusTag(source: DataSource) {
  return (
    <AuthStatusTag
      status={resolveAuthStatus({
        authStatus: source.auth_status,
        configAuthStatus: source.config_json?.auth_status,
        requiresToken: source.requires_token,
      })}
    />
  );
}

function formatDailyBarExchangeCoverage(source: DataSource) {
  const capabilities = getCapabilities(source);
  const exchanges = capabilities.daily_bar_exchanges;
  if (!capabilities.daily_bars || exchanges === null) {
    return null;
  }
  if (!Array.isArray(exchanges) || exchanges.length === 0) {
    return '日线覆盖：未声明交易所范围';
  }
  return `日线覆盖：${exchanges.map((exchange) => formatExchange(exchange)).join(' / ')}`;
}

const preferredSampleFields = [
  'symbol',
  'name',
  'exchange',
  'market',
  'trade_date',
  'pre_close',
  'open',
  'high',
  'low',
  'close',
  'volume',
  'amount',
  'adjust_type',
  'is_open',
  'source',
];

function formatSampleFieldName(field: string) {
  const labels: Record<string, string> = {
    symbol: '代码',
    name: '名称',
    exchange: '交易所',
    market: '市场',
    trade_date: '交易日',
    pre_close: '昨收',
    open: '开盘',
    high: '最高',
    low: '最低',
    close: '收盘',
    volume: '成交量',
    amount: '成交额',
    adjust_type: '复权',
    is_open: '是否开市',
    source: '来源',
  };
  return labels[field] ?? field;
}

function formatSampleValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否';
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? formatNumber(value) : value.toLocaleString('zh-CN', { maximumFractionDigits: 4 });
  }
  return String(value);
}

function getSampleFields(sample: Array<Record<string, unknown>>) {
  const discovered = Array.from(new Set(sample.flatMap((row) => Object.keys(row))));
  const preferred = preferredSampleFields.filter((field) => discovered.includes(field));
  return [...preferred, ...discovered.filter((field) => !preferred.includes(field))].slice(0, 12);
}

function renderSmokeHistory(source: DataSource) {
  const history = source.config_json?.smoke_test_history ?? [];
  if (!history.length) {
    return null;
  }

  return (
    <div className="source-smoke-history-panel">
      <Typography.Text type="secondary">最近 {Math.min(history.length, 5)} 次真实取样，按时间倒序展示。</Typography.Text>
      {history.slice(0, 5).map((item, index) => (
        <div className="source-smoke-history-row" key={`${source.code}-smoke-history-${item.checked_at ?? index}`}>
          <div className="source-smoke-history-main">
            <Typography.Text strong>{formatCapability(item.capability)}</Typography.Text>
            <StatusTag value={item.status} />
            <Typography.Text type="secondary">{formatDateTime(item.checked_at)}</Typography.Text>
          </div>
          <Typography.Text type="secondary">
            原始 {formatNumber(item.raw_records)} / 归一 {formatNumber(item.normalized_records)}
          </Typography.Text>
          {item.message ? (
            <Typography.Text className="source-smoke-history-message" type={item.healthy ? 'secondary' : 'warning'}>
              {item.message}
            </Typography.Text>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function renderSmokeSample(source: DataSource) {
  const lastSmoke = source.config_json?.last_smoke_test;
  if (!lastSmoke) {
    return null;
  }

  const sample = lastSmoke.sample ?? [];
  const validationErrors = lastSmoke.validation_errors ?? [];
  const fields = getSampleFields(sample);
  return (
    <div className="source-smoke-detail">
      <div className="source-smoke-detail-grid">
        <div>
          <Typography.Text type="secondary">取样能力</Typography.Text>
          <Typography.Text strong>{formatCapability(lastSmoke.capability)}</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">取样状态</Typography.Text>
          <StatusTag value={lastSmoke.status} />
        </div>
        <div>
          <Typography.Text type="secondary">记录数</Typography.Text>
          <Typography.Text strong>
            原始 {formatNumber(lastSmoke.raw_records)} / 标准化 {formatNumber(lastSmoke.normalized_records)}
          </Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">检查时间</Typography.Text>
          <Typography.Text strong>{formatDateTime(lastSmoke.checked_at)}</Typography.Text>
        </div>
      </div>
      {lastSmoke.message ? (
        <Typography.Text className="source-smoke-message" type={lastSmoke.healthy ? 'secondary' : 'warning'}>
          {lastSmoke.message}
        </Typography.Text>
      ) : null}
      {validationErrors.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          message={`字段校验发现 ${validationErrors.length} 个问题`}
          description={
            <ul className="source-validation-list">
              {validationErrors.slice(0, 5).map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          }
        />
      ) : null}
      {sample.length ? (
        <div className="source-smoke-sample">
          <Typography.Text strong>标准化样本</Typography.Text>
          <Typography.Text type="secondary">前 {Math.min(sample.length, 3)} 条标准化记录</Typography.Text>
          <div className="source-smoke-sample-grid">
            {sample.slice(0, 3).map((row, index) => (
              <div className="source-smoke-sample-row" key={`${source.code}-sample-${index}`}>
                <Typography.Text type="secondary">样本 {index + 1}</Typography.Text>
                <div className="source-smoke-fields">
                  {fields.map((field) => (
                    <span className="source-smoke-field" key={field}>
                      <Typography.Text type="secondary">{formatSampleFieldName(field)}</Typography.Text>
                      <Typography.Text strong>{formatSampleValue(row[field])}</Typography.Text>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <Alert type="warning" showIcon message="本次没有形成标准化样本" description={lastSmoke.message || '请查看健康状态或重新取样。'} />
      )}
    </div>
  );
}

function renderSourceCard(
  source: DataSource,
  options: {
    onHealthCheck: () => void;
    onSmokeTest: (capability: string) => void;
    onToggleEnabled: (enabled: boolean) => void;
    onUpdatePriority: (priority: number) => void;
    onSyncStockPool: () => void;
    runningSmoke?: string;
    healthLoading?: boolean;
    syncLoading?: boolean;
    updateLoading?: boolean;
    smokeOptions: Array<{ key: string; label: string }>;
    readonly?: boolean;
  },
) {
  const metadata = getMetadata(source);
  const authMode = metadata.auth_mode ?? (source.requires_token ? 'token' : 'none');
  const smokeOptions = smokeCapabilityOptions(source);
  const lastSmoke = source.config_json?.last_smoke_test;
  const smokeHistory = source.config_json?.smoke_test_history ?? [];
  const capabilitySummary = smokeOptions.map((item) => item.label).join(' / ') || '未声明核心能力';
  const smokeSummary = lastSmoke
    ? `${formatCapability(lastSmoke.capability)} ${lastSmoke.healthy ? '通过' : '需处理'}，归一 ${formatNumber(lastSmoke.normalized_records)} 条`
    : '尚未真实取样';

  return (
    <Card
      key={source.code}
      className="source-card"
      size="small"
      title={
        <Space direction="vertical" size={2} className="source-card-title">
          <Space align="center" size={8} wrap>
            <Typography.Text strong>{source.name}</Typography.Text>
            <Typography.Text type="secondary">{source.code}</Typography.Text>
            <StatusTag value={source.health_status} />
            <Tag color={source.enabled ? 'green' : 'default'}>{source.enabled ? '已启用' : '已禁用'}</Tag>
            {options.readonly ? <Tag color="blue">接口恢复后可操作</Tag> : null}
          </Space>
          <Typography.Text type="secondary">{explainSourceAction(source)}</Typography.Text>
        </Space>
      }
      extra={
        <Space wrap size={[6, 6]}>
          <Switch
            checked={source.enabled}
            checkedChildren="启用"
            unCheckedChildren="禁用"
            loading={options.updateLoading}
            onChange={options.onToggleEnabled}
            size="small"
            disabled={options.readonly}
          />
        </Space>
      }
    >
      <div className="source-card-body">
        <div className="source-card-meta">
          <Space wrap size={[4, 4]}>
            <Tag color="geekblue">{formatProviderType(metadata.provider_type ?? 'external_api')}</Tag>
            <Tag color={authMode === 'none' ? 'blue' : 'warning'}>{formatAuthMode(authMode)}</Tag>
            {tokenStatusTag(source)}
            <Tag>{formatStability(metadata.stability ?? 'community')}</Tag>
          </Space>
          <Typography.Text type="secondary">{formatDailyBarExchangeCoverage(source) || '未声明日线覆盖范围'}</Typography.Text>
          <Typography.Text type="secondary">最近检查：{formatDateTime(source.last_checked_at)}</Typography.Text>
        </div>
        <div className="source-card-actions">
          <Space wrap size={[6, 6]}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={options.healthLoading}
              onClick={options.onHealthCheck}
              disabled={options.readonly}
            >
              健康检查
            </Button>
            {options.smokeOptions.map((item) => (
              <Button
                key={item.key}
                size="small"
                icon={<ExperimentOutlined />}
                loading={options.runningSmoke === item.key}
                onClick={() => options.onSmokeTest(item.key)}
                disabled={options.readonly}
              >
                {item.label}
              </Button>
            ))}
            <Tooltip title={source.enabled && Boolean(getCapabilities(source).stock_list) ? '创建股票池同步任务' : '该来源未启用或不支持股票池'}>
              <Button
                size="small"
                icon={<SyncOutlined spin={Boolean(options.syncLoading)} />}
                disabled={options.readonly || !(source.enabled && Boolean(getCapabilities(source).stock_list))}
                loading={options.syncLoading}
                onClick={options.onSyncStockPool}
              >
                同步股票池
              </Button>
            </Tooltip>
          </Space>
        </div>
      </div>
      <div className="source-card-decision-row">
        <div>
          <Typography.Text type="secondary">可用性</Typography.Text>
          <Typography.Text strong>{explainSourceStatus(source)}</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">核心能力</Typography.Text>
          <Typography.Text strong>{capabilitySummary}</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">最近取样</Typography.Text>
          <Typography.Text strong>{smokeSummary}</Typography.Text>
        </div>
      </div>
      <Collapse
        className="source-card-extra-collapse"
        ghost
        size="small"
        items={[
          {
            key: 'details',
            label: '优先级、安装与健康说明',
            children: (
              <div className="source-card-details">
                <div className="source-detail-card source-priority-card">
                  <Typography.Text type="secondary">同步优先级</Typography.Text>
                  <Space size={8} wrap>
                    <InputNumber
                      min={1}
                      max={1000}
                      size="small"
                      value={source.priority}
                      disabled={options.readonly}
                      onChange={(value) => {
                        if (typeof value === 'number' && Number.isFinite(value) && value !== source.priority) {
                          options.onUpdatePriority(value);
                        }
                      }}
                    />
                    <Typography.Text type="secondary">数字越小越优先</Typography.Text>
                  </Space>
                </div>
                <div className="source-detail-card">
                  <Typography.Text type="secondary">适配器</Typography.Text>
                  <Typography.Text>{source.adapter_class || source.config_json?.adapter_class || '-'}</Typography.Text>
                </div>
                <div className="source-detail-card">
                  <Typography.Text type="secondary">安装说明</Typography.Text>
                  <Typography.Text>{metadata.install_note || '无额外安装说明'}</Typography.Text>
                </div>
                <div className="source-detail-card">
                  <Typography.Text type="secondary">上游限制</Typography.Text>
                  <Typography.Text>{metadata.rate_limit_note || '无额外速率说明'}</Typography.Text>
                </div>
                <div className="source-detail-card">
                  <Typography.Text type="secondary">健康说明</Typography.Text>
                  <Typography.Text>{explainSourceStatus(source)}</Typography.Text>
                  <Typography.Text type="secondary">最近检查：{formatDateTime(source.last_checked_at)}</Typography.Text>
                  {source.config_json?.last_health_message ? (
                    <Typography.Text type="secondary">{source.config_json.last_health_message}</Typography.Text>
                  ) : null}
                </div>
              </div>
            ),
          },
          ...(smokeHistory.length
            ? [
                {
                  key: 'history',
                  label: '最近取样历史',
                  children: renderSmokeHistory(source),
                },
              ]
            : []),
          ...(lastSmoke
            ? [
                {
                  key: 'sample',
                  label: '最近取样样本',
                  children: renderSmokeSample(source),
                },
              ]
            : []),
        ]}
      />
    </Card>
  );
}

export function DataSourcesPage() {
  const { message } = AntApp.useApp();
  const pageRef = useRef<HTMLDivElement>(null);
  const query = useDataSourcesQuery();
  const updateMutation = useUpdateDataSourceMutation();
  const healthMutation = useCheckDataSourceHealthMutation();
  const smokeMutation = useSmokeTestDataSourceMutation();
  const syncMutation = useSyncStocksMutation();
  const sources = useMemo(
    () => (query.data ?? []).filter((source) => V1_DATA_SOURCE_CODES.has(source.code)),
    [query.data],
  );
  const isFallbackMode = query.isError && sources.length === 0;
  const displaySources = isFallbackMode ? fallbackDataSources : sources;

  const summary = useMemo(() => {
    const enabled = displaySources.filter((source) => source.enabled).length;
    const healthy = displaySources.filter((source) => source.health_status === 'healthy').length;
    const disabled = displaySources.filter((source) => !source.enabled).length;
    const needsAttention = displaySources.filter(
      (source) => source.enabled && source.health_status !== 'healthy',
    ).length;
    return { enabled, healthy, disabled, needsAttention };
  }, [displaySources]);
  const sourceSections = useMemo(() => {
    const getSourceAttentionRank = (source: DataSource) => {
      if (!source.enabled) {
        return 0;
      }
      if (source.auth_status === 'missing' || source.config_json?.auth_status === 'missing') {
        return 1;
      }
      if (source.health_status === 'unavailable') {
        return 2;
      }
      return 3;
    };
    const sortedSources = [...displaySources].sort((left, right) => {
      const attentionDelta = getSourceAttentionRank(left) - getSourceAttentionRank(right);
      if (attentionDelta !== 0) {
        return attentionDelta;
      }
      const healthDelta = DATA_SOURCE_HEALTH_RANK[left.health_status] - DATA_SOURCE_HEALTH_RANK[right.health_status];
      if (healthDelta !== 0) {
        return healthDelta;
      }
      const priorityDelta = (left.priority ?? Number.MAX_SAFE_INTEGER) - (right.priority ?? Number.MAX_SAFE_INTEGER);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }
      return left.name.localeCompare(right.name, 'zh-CN');
    });
    const needsAttention = sortedSources.filter((source) => source.enabled && source.health_status !== 'healthy');
    const readySources = sortedSources.filter((source) => source.enabled && source.health_status === 'healthy');
    const disabledSources = sortedSources.filter((source) => !source.enabled);
    return [
      {
        key: 'needs-attention',
        title: `需处理 ${needsAttention.length} 个`,
        description: '启用但仍有依赖、凭证或上游问题',
        sources: needsAttention,
      },
      {
        key: 'ready',
        title: `可直接使用 ${readySources.length} 个`,
        description: '健康正常，优先用于取样和同步',
        sources: readySources,
      },
      {
        key: 'disabled',
        title: `已禁用 ${disabledSources.length} 个`,
        description: '暂不参与健康检查和同步',
        sources: disabledSources,
      },
    ].filter((section) => section.sources.length > 0);
  }, [displaySources]);
  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.05, y: 8 });
      const table = root.querySelector('.data-source-table-card');
      if (table) {
        fadeInUp(table, { delay: 0.08, y: 8 });
      }
    },
    { scope: pageRef },
  );

  return (
    <div className="workbench data-sources-page" ref={pageRef}>
      <div className="workbench-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>数据源管理</Typography.Title>
          <Typography.Text type="secondary">先看健康和取样，再展开安装与上游说明</Typography.Text>
        </Space>
      </div>

      <Row gutter={[16, 16]} className="summary-row">
        <Col xs={24} sm={12} xl={6}>
          <Card className="motion-summary-card">
            <Statistic title="注册来源" value={displaySources.length} suffix="个" prefix={<ApiOutlined />} loading={query.isLoading} />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="motion-summary-card">
            <Statistic title="已启用" value={summary.enabled} suffix="个" prefix={<CheckCircleOutlined />} loading={query.isLoading} />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="motion-summary-card">
            <Statistic title="健康来源" value={summary.healthy} suffix="个" prefix={<CheckCircleOutlined />} loading={query.isLoading} />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="需处理"
              value={summary.needsAttention}
              suffix="个"
              prefix={summary.needsAttention > 0 ? <WarningOutlined /> : <FileSearchOutlined />}
              loading={query.isLoading}
            />
          </Card>
        </Col>
      </Row>

      <Alert
        className="data-source-boundary-alert"
        type={isFallbackMode ? 'warning' : 'info'}
        showIcon
        message={isFallbackMode ? '后端数据源接口暂不可用，先展示适配清单' : '这里看的是外部来源状态'}
        description={
          isFallbackMode
            ? '下方是项目内置的五个 V1 适配源预览，等后端恢复后就能进行健康检查、真实取样、启用切换和同步任务。'
            : '健康检查只看依赖、凭证和上游；真实取样只验证字段映射，不写数据库。禁用项会单独列出，覆盖度请看数值汇总。'
        }
      />

      <Card
        className="data-source-table-card"
        title={
          <Space>
            <ExperimentOutlined />
            <span>标准数据源</span>
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void query.refetch()} loading={query.isFetching}>
            刷新
          </Button>
        }
      >
        {query.isError && !isFallbackMode ? (
          <Alert type="error" showIcon message="数据源加载失败" description="后端数据源管理接口暂不可用。" />
        ) : (
          <div className="source-card-sections">
            {sourceSections.map((section) => (
              <section className="source-card-section" key={section.key}>
                  <div className="source-card-section-header">
                    <div className="source-card-section-title">
                      <Typography.Text strong>{section.title}</Typography.Text>
                      <Typography.Text type="secondary">{section.description}</Typography.Text>
                    </div>
                </div>
                <div className="source-card-list">
                  {section.sources.map((source) => {
                    const smokeOptions = smokeCapabilityOptions(source);
                    const runningSmoke =
                      smokeMutation.isPending && smokeMutation.variables?.code === source.code
                        ? smokeMutation.variables.capability
                        : undefined;
                    return renderSourceCard(source, {
                      onHealthCheck: () => {
                        healthMutation.mutate(source.code, {
                          onSuccess: (result) => {
                            if (result.healthy) {
                              void message.success(result.message);
                            } else {
                              void message.warning(result.message);
                            }
                          },
                          onError: (error) => void message.error(error instanceof Error ? error.message : '健康检查失败'),
                        });
                      },
                      onSmokeTest: (capability) => {
                        smokeMutation.mutate(
                          { code: source.code, capability },
                          {
                            onSuccess: (result) => {
                              const summary = `${formatCapability(result.capability)}：原始 ${formatNumber(result.raw_records)} / 归一 ${formatNumber(result.normalized_records)}`;
                              if (result.healthy) {
                                void message.success(`真实取样成功，${summary}`);
                              } else {
                                const validationSummary = result.validation_errors.length
                                  ? `，字段校验 ${formatNumber(result.validation_errors.length)} 个问题`
                                  : '';
                                void message.warning(`${result.message}（${summary}${validationSummary}）`);
                              }
                            },
                            onError: (error) => void message.error(error instanceof Error ? error.message : '真实取样失败'),
                          },
                        );
                      },
                      onToggleEnabled: (enabled) => {
                        updateMutation.mutate(
                          { code: source.code, payload: { enabled } },
                          {
                            onSuccess: () => void message.success(`${source.name} 已${enabled ? '启用' : '禁用'}`),
                            onError: (error) => void message.error(error instanceof Error ? error.message : '数据源状态更新失败'),
                          },
                        );
                      },
                      onUpdatePriority: (priority) => {
                        updateMutation.mutate(
                          { code: source.code, payload: { priority } },
                          {
                            onSuccess: () => void message.success(`${source.name} 优先级已更新`),
                            onError: (error) => void message.error(error instanceof Error ? error.message : '优先级更新失败'),
                          },
                        );
                      },
                      onSyncStockPool: () => {
                        syncMutation.mutate(
                          { source: source.code, market: 'A_SHARE' },
                          {
                            onSuccess: () => void message.success(`${source.name} 股票池同步任务已创建`),
                            onError: (error) => void message.error(error instanceof Error ? error.message : '同步任务创建失败'),
                          },
                        );
                      },
                      runningSmoke,
                      healthLoading: healthMutation.isPending && healthMutation.variables === source.code,
                      syncLoading: syncMutation.isPending && syncMutation.variables?.source === source.code,
                      updateLoading: updateMutation.isPending,
                      smokeOptions,
                      readonly: isFallbackMode,
                    });
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
