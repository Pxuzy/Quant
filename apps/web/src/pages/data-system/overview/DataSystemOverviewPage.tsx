import { useMemo, useRef, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ApiOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  ReadOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  TableOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Empty,
  List,
  Progress,
  Row,
  Skeleton,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import type { DataSource } from '../../../features/data-sources/types';
import { useDataQualityOverviewQuery, useDataQualityReportsQuery } from '../../../features/data-quality/api';
import { useDatabaseIntegrationOverviewQuery, useDatabaseStatusQuery } from '../../../features/database/api';
import type {
  DatabaseCoverageSummary,
  DatasetSnapshot,
  ProviderIntegration,
  RecentIngestBatch,
  SyncWatermark,
} from '../../../features/database/types';
import { useDatasetsQuery } from '../../../features/datasets/api';
import type { Dataset } from '../../../features/datasets/types';
import { useStocksQuery, useSyncStocksMutation } from '../../../features/stocks/api';
import { useSyncTasksQuery } from '../../../features/sync-tasks/api';
import type { SyncTask } from '../../../features/sync-tasks/types';
import { AuthStatusTag, resolveAuthStatus } from '../../../shared/components/AuthStatusTag';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatBytes, formatDate, formatDateTime, formatNumber } from '../../../shared/components/formatters';
import {
  formatCapability,
  formatLayer,
  formatMarket,
  formatStorageType,
  formatTaskType,
  sourceModeLabels,
} from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

const FIRST_PAGE = 1;
const STOCKS_PREVIEW_SIZE = 5;
const DATASETS_PREVIEW_SIZE = 6;
const TASKS_PREVIEW_SIZE = 6;
const REPORTS_PREVIEW_SIZE = 5;
const NEWS_INTERFACE_READY = false;

type AlertItem = {
  key: string;
  title: string;
  description: string;
  status: 'error' | 'warning' | 'info';
};

type KeyFunctionItem = {
  key: string;
  title: string;
  role: string;
  icon: ReactNode;
  statusLabel: string;
  statusColor: string;
  description: string;
  metric: string;
  actionLabel: string;
  onClick: () => void;
  primary?: boolean;
  actionLoading?: boolean;
  actionDisabled?: boolean;
};

// 把任务和日期字段统一成总控台可直接展示的时间信息。
function getTaskTime(task: SyncTask) {
  return task.created_at ?? task.createdAt ?? task.started_at ?? task.startedAt;
}

// 任务列表只关心写入量，避免把原始字段直接摊到页面上。
function getRecordsWritten(task: SyncTask) {
  return task.records_written ?? task.recordsWritten ?? 0;
}

// 同步任务的标题统一走共享标签，保持页面文案一致。
function getTaskTitle(task: SyncTask) {
  return formatTaskType(task.task_type ?? task.taskType ?? 'sync');
}

// 数据集快照的最新日期单独成文，方便卡片快速扫读。
function getDatasetLatestDate(dataset: Dataset) {
  return dataset.latest_data_date ? formatDate(dataset.latest_data_date) : '暂无日期';
}

// 从数据集列表里找出日线快照，作为首页数值判断的入口。
function getDailyBarsSnapshot(snapshots: DatasetSnapshot[]) {
  return snapshots.find((snapshot) => snapshot.dataset_name === 'daily_bars');
}

// 批次和水位线日期有时只有一个边界，统一折成一行展示。
function formatOverviewDateRange(startDate?: string | null, endDate?: string | null) {
  if (!startDate && !endDate) {
    return '-';
  }
  if (startDate && endDate && startDate !== endDate) {
    return `${formatDate(startDate)} ~ ${formatDate(endDate)}`;
  }
  return formatDate(endDate ?? startDate);
}

// 最近批次按照完成时间排序，保证总控台展示的是最新结果。
function batchTime(batch: RecentIngestBatch) {
  const value = batch.finished_at ?? batch.started_at;
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

// 这里保留一个“最近成功批次”的入口，方便一眼看到最新入库情况。
function getLatestRecentBatch(batches: RecentIngestBatch[]) {
  if (!batches.length) {
    return undefined;
  }
  return [...batches].sort((left, right) => batchTime(right) - batchTime(left))[0];
}

// 日线水位线只看 daily_bars，避免和其他数据集混在一起。
function watermarkTime(watermark: SyncWatermark) {
  const value = watermark.last_success_at ?? watermark.latest_success_date;
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

// 选择最新的日线水位线，供顶部结论卡和补数据入口使用。
function getLatestDailyWatermark(watermarks: SyncWatermark[]) {
  return watermarks
    .filter((watermark) => watermark.dataset_name === 'daily_bars')
    .sort((left, right) => watermarkTime(right) - watermarkTime(left))[0];
}

// 这里只保留最值得关注的 provider，避免首屏塞满长列表。
function getTopProviderIntegrations(providers: ProviderIntegration[]) {
  return [...providers]
    .sort((left, right) => right.records_written - left.records_written || right.successes - left.successes)
    .slice(0, 3);
}

// 如果日线存在可补的缺口，就优先把入口导向修复视图。
function getFirstRepairableDailyWatermark(watermarks: SyncWatermark[], prefersMarketRepair: boolean) {
  const repairableDailyWatermarks = watermarks.filter(
    (watermark) => watermark.dataset_name === 'daily_bars' && Boolean(watermark.repair_reason),
  );

  if (prefersMarketRepair) {
    return repairableDailyWatermarks.find((watermark) => !watermark.symbol) ?? repairableDailyWatermarks[0];
  }

  return (
    repairableDailyWatermarks.find(
      (watermark) =>
        Boolean(watermark.symbol) &&
        Boolean(watermark.repair_start_date) &&
        Boolean(watermark.repair_end_date),
    ) ?? repairableDailyWatermarks.find((watermark) => Boolean(watermark.symbol))
  );
}

// 首页只关心“市场日线是否缺口”，不直接暴露后端内部判断细节。
function hasMarketDailyGap(coverage?: DatabaseCoverageSummary) {
  return Boolean(coverage && coverage.daily_missing_symbol_days > 0);
}

// 从数据集列表里抽取一个很短的覆盖摘要，给卡片和标签用。
function summarizeCoverage(datasets: Dataset[]) {
  const sortedDates = datasets
    .map((dataset) => dataset.latest_data_date)
    .filter((date): date is string => Boolean(date))
    .sort();
  const latest = sortedDates[sortedDates.length - 1];

  return {
    latestDate: latest ? formatDate(latest) : '暂无',
    dailyBars: datasets.find((dataset) => dataset.name === 'daily_bars'),
    stockList: datasets.find((dataset) => dataset.name === 'stock_list'),
    calendar: datasets.find((dataset) => dataset.name === 'trading_calendars' || dataset.name === 'calendars'),
  };
}

// 数据源能力来自配置 JSON，只有启用的能力才在卡片里展示。
function sourceCapabilities(source: DataSource) {
  const capabilities = source.config_json?.capabilities ?? {};
  return Object.entries(capabilities)
    .filter(([, enabled]) => Boolean(enabled))
    .map(([capability]) => capability);
}

// 总控台的异常提醒只聚合最关键的风险，不把每个接口错误都原样堆上来。
function buildWorkbenchAlerts({
  sources,
  tasks,
  failedBatches,
  qualityErrorCount,
  dataLakeSize,
}: {
  sources: DataSource[];
  tasks: SyncTask[];
  failedBatches: RecentIngestBatch[];
  qualityErrorCount: number;
  dataLakeSize?: number | null;
}) {
  const alerts: AlertItem[] = [];
  const unhealthySources = sources.filter(
    (source) => source.health_status === 'unhealthy' || source.health_status === 'unavailable',
  );
  const failedTasks = tasks.filter((task) => task.status === 'failed');

  if (unhealthySources.length > 0) {
    alerts.push({
      key: 'sources',
      title: `${unhealthySources.length} 个数据源需关注`,
      description: unhealthySources.map((source) => source.name).join('、'),
      status: 'warning',
    });
  }

  if (failedTasks.length > 0) {
    alerts.push({
      key: 'tasks',
      title: `最近同步失败 ${failedTasks.length} 个`,
      description: failedTasks
        .slice(0, 3)
        .map((task) => `#${task.id} ${getTaskTitle(task)}`)
        .join('、'),
      status: 'error',
    });
  }

  if (failedBatches.length > 0) {
    alerts.push({
      key: 'batches',
      title: `数据整合批次失败 ${failedBatches.length} 个`,
      description: failedBatches
        .slice(0, 3)
        .map((batch) => `#${batch.id} ${formatTaskType(batch.dataset_name)}`)
        .join('、'),
      status: 'error',
    });
  }

  if (qualityErrorCount > 0) {
    alerts.push({
      key: 'quality',
      title: `质量错误 ${qualityErrorCount} 条`,
      description: '进入数据库管理查看缺失、重复和异常价格等质量报告',
      status: 'error',
    });
  }

  if ((dataLakeSize ?? 0) <= 0) {
    alerts.push({
      key: 'lake',
      title: '行情数据湖暂无容量',
      description: '日线行情可能还没有完成正式写入',
      status: 'info',
    });
  }

  return alerts;
}

// 数据源健康模块：帮用户快速看外部接口可用性、授权和能力声明。
function SourceHealthPanel({
  sources,
  loading,
  error,
  onRefresh,
  onOpen,
}: {
  sources: DataSource[];
  loading: boolean;
  error: unknown;
  onRefresh: () => void;
  onOpen: () => void;
}) {
  return (
    <Card
      className="overview-panel overview-source-panel"
      title="数据源健康"
      extra={
        <Space className="overview-panel-actions">
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
            刷新
          </Button>
          <Button size="small" icon={<RightOutlined />} onClick={onOpen}>
            进入数据源
          </Button>
        </Space>
      }
    >
      {error ? (
        <Alert type="error" showIcon message="数据源状态加载失败" description="后端数据源接口暂不可用。" />
      ) : loading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : sources.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据源" />
      ) : (
        <List
          className="overview-source-list"
          dataSource={sources}
          renderItem={(source) => (
            <List.Item>
              <Space className="overview-source-item" direction="vertical" size={8}>
                <Space className="overview-source-heading">
                  <Typography.Text strong>{source.name}</Typography.Text>
                  <StatusTag value={source.health_status} />
                </Space>
                <Space wrap size={[4, 4]}>
                  <Tag color={source.enabled ? 'green' : 'default'}>
                    {source.enabled ? '已启用' : '已禁用'}
                  </Tag>
                  <AuthStatusTag
                    status={resolveAuthStatus({
                      authStatus: source.auth_status,
                      configAuthStatus: source.config_json?.auth_status,
                      requiresToken: source.requires_token,
                    })}
                  />
                  <Tag>优先级 {source.priority}</Tag>
                </Space>
                <Space wrap size={[4, 4]}>
                  {sourceCapabilities(source).length > 0 ? (
                    sourceCapabilities(source).map((capability) => <Tag key={capability}>{formatCapability(capability)}</Tag>)
                  ) : (
                    <Tag>未声明能力</Tag>
                  )}
                </Space>
                <Typography.Text type="secondary">
                  最近检查：{formatDateTime(source.last_checked_at)}
                </Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

// 数据覆盖模块：只展示数据集数量、最新日期和少量覆盖标签。
function DatasetCoveragePanel({
  datasets,
  total,
  loading,
  error,
  onRefresh,
  onOpen,
}: {
  datasets: Dataset[];
  total: number;
  loading: boolean;
  error: unknown;
  onRefresh: () => void;
  onOpen: () => void;
}) {
  const coverage = summarizeCoverage(datasets);

  return (
    <Card
      className="overview-panel"
      title="数据库内容覆盖"
      extra={
        <Space className="overview-panel-actions">
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
            刷新
          </Button>
          <Button size="small" icon={<RightOutlined />} onClick={onOpen}>
            进入数据库
          </Button>
        </Space>
      }
    >
      {error ? (
        <Alert type="error" showIcon message="数据库内容加载失败" description="后端数据集接口暂不可用。" />
      ) : loading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : (
        <Space className="overview-catalog" direction="vertical" size={14}>
          <div className="overview-catalog-strip">
            <div>
              <Typography.Text type="secondary">数据内容</Typography.Text>
              <Typography.Title level={4}>{formatNumber(total)}</Typography.Title>
            </div>
            <div>
              <Typography.Text type="secondary">最新数据日</Typography.Text>
              <Typography.Title level={4}>{coverage.latestDate}</Typography.Title>
            </div>
          </div>

          <Space wrap size={[8, 8]}>
            <Tag color={coverage.stockList ? 'green' : 'default'}>股票列表</Tag>
            <Tag color={coverage.dailyBars ? 'blue' : 'default'}>日线行情</Tag>
            <Tag color={coverage.calendar ? 'cyan' : 'default'}>交易日历</Tag>
          </Space>

          <List
            className="overview-dataset-list"
            dataSource={datasets}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据集" /> }}
            renderItem={(dataset) => (
              <List.Item>
                <Space className="overview-dataset-row" align="center">
                  <div>
                    <Typography.Text strong>{formatCapability(dataset.name)}</Typography.Text>
                    <Typography.Text type="secondary">
                      {formatLayer(dataset.layer)} / {formatStorageType(dataset.storage_type)}
                    </Typography.Text>
                  </div>
                  <div>
                    <Typography.Text>{formatNumber(dataset.row_count)} 行</Typography.Text>
                    <Typography.Text type="secondary">{getDatasetLatestDate(dataset)}</Typography.Text>
                  </div>
                  <StatusTag value={dataset.quality_status} />
                </Space>
              </List.Item>
            )}
          />
        </Space>
      )}
    </Card>
  );
}

// 最近同步模块：让用户直接看到任务状态、市场、来源和写入量。
function RecentTaskPanel({
  tasks,
  loading,
  error,
  onRefresh,
  onOpen,
}: {
  tasks: SyncTask[];
  loading: boolean;
  error: unknown;
  onRefresh: () => void;
  onOpen: () => void;
}) {
  return (
    <Card
      className="overview-panel"
      title="最近同步记录"
      extra={
        <Space className="overview-panel-actions">
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
            刷新
          </Button>
          <Button size="small" icon={<RightOutlined />} onClick={onOpen}>
            进入调度
          </Button>
        </Space>
      }
    >
      {error ? (
        <Alert type="error" showIcon message="同步记录加载失败" description="后端任务接口暂不可用。" />
      ) : loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : tasks.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无同步记录" />
      ) : (
        <List
          className="overview-task-list"
          dataSource={tasks}
          renderItem={(task) => {
            const progress = task.progress ?? (task.status === 'success' ? 100 : 0);
            return (
              <List.Item>
                <Space className="overview-task-item" direction="vertical" size={8}>
                  <Space className="overview-task-heading">
                    <Typography.Text strong>{getTaskTitle(task)}</Typography.Text>
                    <StatusTag value={task.status} />
                  </Space>
                  <Space className="task-meta" split={<span className="meta-dot" />}>
                    <span>{formatMarket(task.market, '全部市场')}</span>
                    <span>{task.source === 'auto' ? sourceModeLabels.auto : task.source || '未指定来源'}</span>
                    <span>写入 {formatNumber(getRecordsWritten(task))}</span>
                  </Space>
                  <Progress
                    percent={Math.max(0, Math.min(100, Number(progress)))}
                    size="small"
                    status={task.status === 'failed' ? 'exception' : undefined}
                  />
                  <Space className="task-time">
                    <ClockCircleOutlined />
                    <Typography.Text type="secondary">{formatDateTime(getTaskTime(task))}</Typography.Text>
                  </Space>
                </Space>
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
}

// 异常提醒模块：把数据源、任务、批次和质量错误聚成一列。
function WorkbenchAlertsPanel({
  alerts,
  loading,
  error,
  onRefresh,
  onOpen,
}: {
  alerts: AlertItem[];
  loading: boolean;
  error: unknown;
  onRefresh: () => void;
  onOpen: () => void;
}) {
  const statusColor = {
    error: 'red',
    warning: 'orange',
    info: 'blue',
  } as const;

  return (
    <Card
      className="overview-panel overview-alert-panel"
      title="异常提醒"
      extra={
        <Space className="overview-panel-actions">
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
            刷新
          </Button>
          <Button size="small" icon={<RightOutlined />} onClick={onOpen}>
            进入数据库
          </Button>
        </Space>
      }
    >
      {error ? (
        <Alert type="error" showIcon message="异常状态加载失败" description="部分总览接口暂不可用。" />
      ) : loading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : alerts.length === 0 ? (
        <Alert type="success" showIcon message="当前没有需要立即处理的异常" description="数据源、同步任务、批次和质量错误处于可接受状态。" />
      ) : (
        <List
          className="overview-alert-list"
          dataSource={alerts}
          renderItem={(item) => (
            <List.Item>
              <Space className="overview-alert-item" direction="vertical" size={6}>
                <Space className="overview-alert-heading">
                  <WarningOutlined />
                  <Typography.Text strong>{item.title}</Typography.Text>
                  <Tag color={statusColor[item.status]}>{item.status === 'error' ? '错误' : item.status === 'warning' ? '警告' : '提示'}</Tag>
                </Space>
                <Typography.Text type="secondary">{item.description}</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

// 数据闭环模块：把覆盖、水位线、最近批次和 provider 表现放到一起。
function DataLineagePanel({
  coverage,
  watermark,
  latestBatch,
  providers,
  loading,
  error,
  onOpenDatabase,
  onOpenTask,
}: {
  coverage?: DatabaseCoverageSummary;
  watermark?: SyncWatermark;
  latestBatch?: RecentIngestBatch;
  providers: ProviderIntegration[];
  loading: boolean;
  error: unknown;
  onOpenDatabase: () => void;
  onOpenTask: (taskId: string | number) => void;
}) {
  const completeness =
    coverage?.daily_completeness === undefined || coverage.daily_completeness === null
      ? '-'
      : `${Math.round(coverage.daily_completeness * 100)}%`;

  return (
    <Card
      className="overview-panel overview-lineage-panel"
      title="数据闭环追踪"
      extra={
        <Button size="small" icon={<RightOutlined />} onClick={onOpenDatabase}>
          进入数据库
        </Button>
      }
    >
      {error ? (
        <Alert type="error" showIcon message="数据闭环信息加载失败" description="数据库整合总览接口暂不可用。" />
      ) : loading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : (
        <div className="overview-lineage-grid">
          <div>
            <Typography.Text type="secondary">日线覆盖缺口</Typography.Text>
            <Typography.Title level={4}>{formatNumber(coverage?.daily_missing_symbol_days ?? 0)}</Typography.Title>
            <Typography.Text type="secondary">
              已有 {formatNumber(coverage?.daily_actual_symbol_days ?? 0)} / 应有 {formatNumber(coverage?.daily_expected_symbol_days ?? 0)}
            </Typography.Text>
            <Space wrap size={[6, 6]}>
              <Tag color="blue">完整度 {completeness}</Tag>
              <Tag>交易日历 {formatDate(coverage?.calendar_latest_date)}</Tag>
            </Space>
          </div>

          <div>
            <Typography.Text type="secondary">最近成功水位线</Typography.Text>
            <Typography.Title level={4}>{formatDate(watermark?.latest_success_date)}</Typography.Title>
            <Typography.Text type="secondary">
              {watermark ? `${watermark.source || '-'} / 请求 ${watermark.requested_source || '-'}` : '暂无日线水位线'}
            </Typography.Text>
            <Space wrap size={[6, 6]}>
              <StatusTag value={watermark?.quality_status} />
              {watermark?.repair_reason ? <Tag color="warning">{watermark.repair_reason}</Tag> : <Tag color="green">无需补齐</Tag>}
            </Space>
          </div>

          <div>
            <Typography.Text type="secondary">最近入库批次</Typography.Text>
            {latestBatch ? (
              <>
                <Space wrap size={6}>
                  <Typography.Title level={4}>#{latestBatch.id}</Typography.Title>
                  <StatusTag value={latestBatch.status} />
                  <StatusTag value={latestBatch.quality_status} />
                </Space>
                <Typography.Text type="secondary">
                  {formatTaskType(latestBatch.dataset_name)} / {formatOverviewDateRange(latestBatch.start_date, latestBatch.end_date)}
                </Typography.Text>
                <Typography.Text type="secondary">
                  来源 {latestBatch.source || '-'}，请求 {latestBatch.requested_source || '-'}，写入 {formatNumber(latestBatch.records_written)} 行
                </Typography.Text>
                <Typography.Text type="secondary">
                  Schema {latestBatch.schema_version} / Normalize {latestBatch.normalize_version}
                </Typography.Text>
                <Button size="small" type="link" icon={<RightOutlined />} onClick={() => onOpenTask(latestBatch.task_id)}>
                  查看任务 #{latestBatch.task_id}
                </Button>
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无入库批次" />
            )}
          </div>

          <div>
            <Typography.Text type="secondary">Provider 写入表现</Typography.Text>
            {providers.length ? (
              <div className="overview-provider-mini-list">
                {providers.map((provider) => (
                  <div key={provider.source}>
                    <Space className="overview-provider-mini-heading">
                      <Typography.Text strong>{provider.source}</Typography.Text>
                      <Tag color={provider.failures ? 'warning' : 'green'}>{provider.failures ? '需关注' : '稳定'}</Tag>
                    </Space>
                    <Typography.Text type="secondary">
                      成功 {formatNumber(provider.successes)} / 失败 {formatNumber(provider.failures)} / 降级成功 {formatNumber(provider.fallback_successes)}
                    </Typography.Text>
                    <Typography.Text type="secondary">写入 {formatNumber(provider.records_written)} 行</Typography.Text>
                  </div>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 provider 写入记录" />
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export function DataSystemOverviewPage() {
  const { message } = AntApp.useApp();
  const navigate = useNavigate();
  const pageRef = useRef<HTMLDivElement>(null);

  // 先拉各业务域的首页快照，结论卡和入口文案都依赖这些结果。
  const stocksQuery = useStocksQuery({ market: 'A_SHARE', page: FIRST_PAGE, pageSize: STOCKS_PREVIEW_SIZE });
  const dataSourcesQuery = useDataSourcesQuery();
  const datasetsQuery = useDatasetsQuery({ page: FIRST_PAGE, pageSize: DATASETS_PREVIEW_SIZE });
  const databaseStatusQuery = useDatabaseStatusQuery();
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: 'A_SHARE' });
  const qualityOverviewQuery = useDataQualityOverviewQuery();
  const qualityReportsQuery = useDataQualityReportsQuery({
    severity: 'error',
    page: FIRST_PAGE,
    pageSize: REPORTS_PREVIEW_SIZE,
  });
  const tasksQuery = useSyncTasksQuery({ page: FIRST_PAGE, pageSize: TASKS_PREVIEW_SIZE });
  const syncStocksMutation = useSyncStocksMutation();

  const stocks = stocksQuery.data?.items ?? [];
  const sources = dataSourcesQuery.data ?? [];
  const datasets = datasetsQuery.data?.items ?? [];
  const tasks = tasksQuery.data?.items ?? [];
  const reports = qualityReportsQuery.data?.items ?? [];
  const overview = qualityOverviewQuery.data;
  const databaseStatus = databaseStatusQuery.data;
  const integrationOverview = integrationOverviewQuery.data;
  const integrationSummary = integrationOverview?.summary;
  const coverageSummary = integrationOverview?.coverage_summary;
  const dailyBarsSnapshot = getDailyBarsSnapshot(integrationOverview?.dataset_snapshots ?? []);

  // 这些派生状态只负责把原始数据压成首页判断，不在渲染里临时拼逻辑。
  const latestRecentBatch = useMemo(
    () => getLatestRecentBatch(integrationOverview?.recent_batches ?? []),
    [integrationOverview?.recent_batches],
  );
  const latestDailyWatermark = useMemo(
    () => getLatestDailyWatermark(integrationOverview?.sync_watermarks ?? []),
    [integrationOverview?.sync_watermarks],
  );
  const topProviderIntegrations = useMemo(
    () => getTopProviderIntegrations(integrationOverview?.provider_integrations ?? []),
    [integrationOverview?.provider_integrations],
  );
  const dailySyncNavigationLoading = integrationOverviewQuery.isLoading || integrationOverviewQuery.isFetching;
  const shouldOpenMarketDailyRepair = hasMarketDailyGap(coverageSummary);
  const repairableDailyWatermark = getFirstRepairableDailyWatermark(
    integrationOverview?.sync_watermarks ?? [],
    shouldOpenMarketDailyRepair,
  );
  const latestDailyDate = dailyBarsSnapshot?.latest_data_date ?? integrationSummary?.latest_data_date;
  const failedBatches = useMemo(
    () => (integrationOverview?.recent_batches ?? []).filter((batch) => batch.status === 'failed'),
    [integrationOverview?.recent_batches],
  );

  const sourceSummary = useMemo(() => {
    const enabled = sources.filter((source) => source.enabled).length;
    const unhealthy = sources.filter((source) => source.health_status === 'unhealthy' || source.health_status === 'unavailable').length;
    const healthy = sources.filter((source) => source.health_status === 'healthy').length;
    return { enabled, unhealthy, healthy };
  }, [sources]);

  const taskSummary = useMemo(() => {
    const active = tasks.filter((task) => task.status === 'pending' || task.status === 'running').length;
    const failed = tasks.filter((task) => task.status === 'failed').length;
    return { active, failed };
  }, [tasks]);

  // 数值汇总和决策文案都依赖这两个百分比，单独算出来更清楚。
  const qualityPassRate = useMemo(() => {
    if (!overview?.datasets_total) {
      return 0;
    }
    return Math.round((overview.datasets_good / overview.datasets_total) * 100);
  }, [overview]);

  const coveragePercent = useMemo(() => {
    if (coverageSummary?.daily_completeness === undefined || coverageSummary.daily_completeness === null) {
      return 0;
    }
    return Math.round(coverageSummary.daily_completeness * 100);
  }, [coverageSummary?.daily_completeness]);

  // 顶部提醒只呈现最值得处理的异常，不把整页做成告警面板。
  const alerts = useMemo(
    () =>
      buildWorkbenchAlerts({
        sources,
        tasks,
        failedBatches,
        qualityErrorCount: overview?.reports_error ?? 0,
        dataLakeSize: databaseStatus?.data_lake_size_bytes,
      }),
    [databaseStatus?.data_lake_size_bytes, failedBatches, overview?.reports_error, sources, tasks],
  );

  const openStocks = () => void navigate({ to: '/data-system/stocks' });
  const openNumericSummary = () => void navigate({ to: '/data-system/numeric-summary' });
  const openNewsSummary = () => void navigate({ to: '/data-system/news-summary' });
  const openSources = () => void navigate({ to: '/data-system/data-sources' });
  const openDatabase = () => void navigate({ to: '/data-system/database' });
  const openQuality = () => void navigate({ to: '/data-system/database' });
  const openTasks = () => void navigate({ to: '/data-system/sync-tasks' });
  const openTaskDetail = (taskId: string | number) => {
    const numericTaskId = Number(taskId);
    void navigate({
      to: '/data-system/sync-tasks',
      search: {
        taskId: Number.isFinite(numericTaskId) ? numericTaskId : undefined,
        page: 1,
        pageSize: 10,
      },
    });
  };

  // 补数据入口会带上市场、日期和来源，减少手动补参。
  const openDailySync = () => {
    const focus = shouldOpenMarketDailyRepair ? 'daily-bars-market-repair' : 'daily-bars';
    void navigate({
      to: '/data-system/sync-tasks',
      search: {
        focus,
        market: repairableDailyWatermark?.market ?? coverageSummary?.market ?? undefined,
        symbol: focus === 'daily-bars' ? repairableDailyWatermark?.symbol ?? undefined : undefined,
        startDate: repairableDailyWatermark?.repair_start_date ?? coverageSummary?.coverage_start_date ?? undefined,
        endDate: repairableDailyWatermark?.repair_end_date ?? coverageSummary?.coverage_end_date ?? undefined,
        syncSource: repairableDailyWatermark?.requested_source || repairableDailyWatermark?.source || undefined,
      },
    });
  };

  // 刷新只重新抓首页状态，不在这里拼业务逻辑。
  const refreshOverview = () => {
    void stocksQuery.refetch();
    void dataSourcesQuery.refetch();
    void datasetsQuery.refetch();
    void databaseStatusQuery.refetch();
    void integrationOverviewQuery.refetch();
    void qualityOverviewQuery.refetch();
    void qualityReportsQuery.refetch();
    void tasksQuery.refetch();
  };

  const handleSyncStocks = () => {
    syncStocksMutation.mutate(
      { source: 'auto', market: 'A_SHARE' },
      {
        onSuccess: (task) => {
          void message.success(`股票池同步任务已创建${task.id ? ` #${task.id}` : ''}`);
          refreshOverview();
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '股票池同步任务创建失败');
        },
      },
    );
  };

  // 决策卡只给一个最该先做的动作，避免首页同时给出太多命令。
  const dailyMissingSymbolDays = coverageSummary?.daily_missing_symbol_days ?? 0;
  const hasDailyCoverageGap = dailyMissingSymbolDays > 0;
  const hasSourceIssue = sourceSummary.unhealthy > 0;
  const hasExecutionIssue =
    taskSummary.failed > 0 || (integrationSummary?.failed_batches_total ?? 0) > 0 || (overview?.reports_error ?? 0) > 0;
  const decisionTone = hasExecutionIssue ? 'danger' : hasDailyCoverageGap || hasSourceIssue ? 'warning' : 'success';
  const decisionTitle = hasDailyCoverageGap
    ? '先补日线覆盖'
    : hasSourceIssue
      ? '先处理数据源健康'
      : hasExecutionIssue
        ? '先看失败任务和质量错误'
        : '数值底座可继续使用';
  const decisionDescription = hasDailyCoverageGap
    ? `A 股日线还有 ${formatNumber(dailyMissingSymbolDays)} 个股票交易日缺口，先进入数值汇总确认范围，再补齐日线。`
    : hasSourceIssue
      ? `${sourceSummary.unhealthy} 个数据源不可用或不健康，先检查鉴权、安装和上游限制。`
      : hasExecutionIssue
        ? `最近失败任务 ${formatNumber(taskSummary.failed)} 个，质量错误 ${formatNumber(overview?.reports_error ?? 0)} 条。`
        : `股票池、新闻汇总、数值数据、数据源管理、同步调度和数据库管理都处于可用状态，可以直接继续查看。`;
  const decisionActionLabel = hasDailyCoverageGap
    ? '打开数值汇总'
    : hasSourceIssue
      ? '检查数据源'
    : hasExecutionIssue
      ? '查看数据库状态'
      : '查看数值汇总';
  const handleDecisionAction = hasSourceIssue ? openSources : hasExecutionIssue ? openDatabase : openNumericSummary;
  const databaseTotalSize = (databaseStatus?.database_size_bytes ?? 0) + (databaseStatus?.data_lake_size_bytes ?? 0);

  // 关键功能清单把七个日常入口摆在同一屏：先解释用途，再给状态信号和下一步动作。
  const keyFunctionItems: KeyFunctionItem[] = [
    {
      key: 'overview',
      title: '总控台',
      role: '每天先看',
      icon: <DashboardOutlined />,
      statusLabel: alerts.length ? `${alerts.length} 个提醒` : '状态汇总',
      statusColor: alerts.length ? 'warning' : 'blue',
      description: '汇总当前结论、异常提醒和最短处理路径。',
      metric: `完整度 ${coveragePercent}% / 数据源 ${sourceSummary.healthy}/${sources.length || 0}`,
      actionLabel: '刷新状态',
      onClick: refreshOverview,
    },
    {
      key: 'numeric-summary',
      title: '数值数据',
      role: '先判断能不能用',
      icon: <BarChartOutlined />,
      statusLabel: hasDailyCoverageGap ? '先补覆盖' : '可用',
      statusColor: hasDailyCoverageGap ? 'warning' : 'green',
      description: '看日线新鲜度、覆盖率、质量风险和最近批次。',
      metric: `缺口 ${formatNumber(dailyMissingSymbolDays)} / 最新 ${latestDailyDate ? formatDate(latestDailyDate) : '暂无'}`,
      actionLabel: '打开数值汇总',
      onClick: openNumericSummary,
      primary: true,
    },
    {
      key: 'news-summary',
      title: '新闻汇总',
      role: '看事件和情绪',
      icon: <ReadOutlined />,
      statusLabel: NEWS_INTERFACE_READY ? '已接入' : '结构已备',
      statusColor: NEWS_INTERFACE_READY ? 'green' : 'warning',
      description: '聚合公告、资讯、研报、政策动态和关联股票。',
      metric: '主题聚类 / 情绪分布 / 影响分',
      actionLabel: '打开新闻汇总',
      onClick: openNewsSummary,
    },
    {
      key: 'stocks',
      title: '股票池',
      role: '证券目录',
      icon: <TableOutlined />,
      statusLabel: stocksQuery.isLoading ? '加载中' : 'A 股',
      statusColor: 'blue',
      description: '维护代码、名称、交易所、市场、行业和启停状态。',
      metric: stocksQuery.isLoading ? '加载中' : `${formatNumber(stocksQuery.data?.total ?? 0)} 只股票`,
      actionLabel: '打开股票池',
      onClick: openStocks,
    },
    {
      key: 'data-sources',
      title: '数据源管理',
      role: '外部接口入口',
      icon: <ApiOutlined />,
      statusLabel: hasSourceIssue ? '需处理' : '健康',
      statusColor: hasSourceIssue ? 'warning' : 'green',
      description: '检查 stock-sdk、adata、AkShare、BaoStock、TuShare 等来源。',
      metric: `已启用 ${formatNumber(sourceSummary.enabled)} / 健康 ${formatNumber(sourceSummary.healthy)}`,
      actionLabel: '检查数据源',
      onClick: openSources,
    },
    {
      key: 'sync-tasks',
      title: '同步调度',
      role: '补数和任务',
      icon: <SyncOutlined />,
      statusLabel: taskSummary.failed > 0 ? '有失败' : taskSummary.active > 0 ? '运行中' : '待执行',
      statusColor: taskSummary.failed > 0 ? 'red' : taskSummary.active > 0 ? 'processing' : 'blue',
      description: '创建股票池、日线、交易日历同步和缺口修复任务。',
      metric: `运行 ${formatNumber(taskSummary.active)} / 失败 ${formatNumber(taskSummary.failed)}`,
      actionLabel: shouldOpenMarketDailyRepair ? '补齐日线' : '打开调度',
      onClick: openDailySync,
      actionLoading: dailySyncNavigationLoading,
      actionDisabled: dailySyncNavigationLoading,
    },
    {
      key: 'database',
      title: '数据库管理',
      role: '质量和存储',
      icon: <DatabaseOutlined />,
      statusLabel: databaseStatus?.duckdb_engine_status === 'available' ? '可查询' : '需确认',
      statusColor: databaseStatus?.duckdb_engine_status === 'available' ? 'cyan' : 'warning',
      description: '查看元数据库、数据湖、DuckDB、目录和质量报告。',
      metric: `${formatBytes(databaseTotalSize)} / Parquet ${formatNumber(databaseStatus?.parquet_file_count ?? 0)}`,
      actionLabel: '打开数据库',
      onClick: openDatabase,
    },
  ];

  // 股票池模块：给用户一个最直接的证券池入口和可用性快照。
  const stockSnapshotPanel = (
    <Card
      className="overview-panel overview-stock-panel"
      title="股票池快照"
      extra={
        <Button size="small" icon={<RightOutlined />} onClick={openStocks}>
          进入股票池
        </Button>
      }
    >
      {stocksQuery.isError ? (
        <Alert type="error" showIcon message="股票池加载失败" description="后端股票接口暂不可用。" />
      ) : stocksQuery.isLoading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : stocks.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无股票记录" />
      ) : (
        <div className="overview-stock-table">
          <div className="overview-stock-table-head">
            <span>代码</span>
            <span>名称</span>
            <span>市场</span>
            <span>行业</span>
            <span>状态</span>
          </div>
          {stocks.map((stock) => (
            <div className="overview-stock-table-row" key={`${stock.symbol}-${stock.exchange}`}>
              <Typography.Text strong>{stock.symbol}</Typography.Text>
              <Typography.Text>{stock.name}</Typography.Text>
              <Typography.Text type="secondary">{formatMarket(stock.market)}</Typography.Text>
              <Typography.Text type="secondary">{stock.industry || '未分类'}</Typography.Text>
              <StatusTag value={stock.status} />
            </div>
          ))}
        </div>
      )}
    </Card>
  );

  // 质量风险模块：保留最近检查和错误报告，方便快速定位数据质量问题。
  const qualityRiskPanel = (
    <Card
      className="overview-panel"
      title="质量风险"
      extra={
        <Space className="overview-panel-actions">
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={qualityOverviewQuery.isFetching || qualityReportsQuery.isFetching}
            onClick={() => {
              void qualityOverviewQuery.refetch();
              void qualityReportsQuery.refetch();
            }}
          >
            刷新
          </Button>
          <Button size="small" icon={<RightOutlined />} onClick={openQuality}>
            进入数据库
          </Button>
        </Space>
      }
    >
      {qualityOverviewQuery.isError || qualityReportsQuery.isError ? (
        <Alert type="error" showIcon message="质量信息加载失败" description="后端质量接口暂不可用。" />
      ) : qualityOverviewQuery.isLoading || qualityReportsQuery.isLoading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : (
        <Space className="overview-quality" direction="vertical" size={14}>
          <div className="overview-quality-score">
            <Progress
              type="circle"
              percent={qualityPassRate}
              size={86}
              status={(overview?.reports_error ?? 0) > 0 ? 'exception' : undefined}
            />
            <div>
              <Typography.Text type="secondary">最近检查</Typography.Text>
              <Typography.Title level={5}>{formatDateTime(overview?.latest_checked_at)}</Typography.Title>
              <Typography.Text type="secondary">数据集 {formatNumber(overview?.datasets_total ?? 0)} 个</Typography.Text>
            </div>
          </div>
          <List
            className="overview-quality-list"
            dataSource={reports}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无错误报告" /> }}
            renderItem={(report) => (
              <List.Item>
                <Space direction="vertical" size={4}>
                  <Space>
                    <WarningOutlined />
                    <Typography.Text strong>{formatCapability(report.dataset_name)}</Typography.Text>
                    <StatusTag value={report.status} />
                  </Space>
                  <Typography.Text type="secondary">{report.message}</Typography.Text>
                  <Typography.Text type="secondary">{formatDateTime(report.checked_at)}</Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        </Space>
      )}
    </Card>
  );

  // 存储状态模块：把元数据库、数据湖和执行引擎放在一张卡里。
  const storagePanel = (
    <Card className="overview-panel overview-storage-panel" title="数据库状态">
      {databaseStatusQuery.isError || integrationOverviewQuery.isError ? (
        <Alert type="error" showIcon message="数据库状态加载失败" description="后端数据库总览接口暂不可用。" />
      ) : databaseStatusQuery.isLoading || integrationOverviewQuery.isLoading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : (
        <Space className="overview-storage-list" direction="vertical" size={10}>
          <div>
            <Typography.Text type="secondary">当前元数据库</Typography.Text>
            <Typography.Text strong>{databaseStatus?.database_kind || '-'}</Typography.Text>
            <Typography.Text type="secondary">{databaseStatus?.database_role || '-'}</Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">行情数据湖</Typography.Text>
            <Typography.Text strong>{formatBytes(databaseStatus?.data_lake_size_bytes)}</Typography.Text>
            <Typography.Text type="secondary">
              文件 {formatNumber(databaseStatus?.total_file_count ?? 0)} / Parquet {formatNumber(databaseStatus?.parquet_file_count ?? 0)}
            </Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">DuckDB 查询引擎</Typography.Text>
            <Space wrap size={6}>
              <Typography.Text strong>{databaseStatus?.duckdb_engine_status === 'available' ? '可用' : '不可用'}</Typography.Text>
              <Tag color={databaseStatus?.duckdb_engine_status === 'available' ? 'green' : 'warning'}>
                {databaseStatus?.duckdb_engine_status || '-'}
              </Tag>
            </Space>
            <Typography.Text type="secondary">{databaseStatus?.duckdb_engine_note || '-'}</Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">全量目录</Typography.Text>
            <Typography.Text strong>{formatNumber(integrationSummary?.datasets_total ?? datasetsQuery.data?.total ?? 0)} 个数据集</Typography.Text>
            <Typography.Text type="secondary">记录 {formatNumber(integrationSummary?.total_rows ?? 0)} 行</Typography.Text>
          </div>
          <Button size="small" icon={<RightOutlined />} onClick={openDatabase}>
            查看数据库管理
          </Button>
        </Space>
      )}
    </Card>
  );

  // 详细诊断分成三组：数值链路、来源与任务、质量与存储。
  const diagnosticsTabs = [
    {
      key: 'numeric',
      // 数值链路：默认展开的主诊断面板。
      label: '数值链路',
      children: (
        <Row gutter={[14, 14]} className="overview-diagnostic-grid" align="stretch">
          <Col span={24}>
            <DataLineagePanel
              coverage={coverageSummary}
              watermark={latestDailyWatermark}
              latestBatch={latestRecentBatch}
              providers={topProviderIntegrations}
              loading={integrationOverviewQuery.isLoading || integrationOverviewQuery.isFetching}
              error={integrationOverviewQuery.isError ? integrationOverviewQuery.error : null}
              onOpenDatabase={openDatabase}
              onOpenTask={openTaskDetail}
            />
          </Col>
          <Col span={14}>{stockSnapshotPanel}</Col>
          <Col span={10}>
            <DatasetCoveragePanel
              datasets={datasets}
              total={datasetsQuery.data?.total ?? 0}
              loading={datasetsQuery.isLoading || datasetsQuery.isFetching}
              error={datasetsQuery.isError ? datasetsQuery.error : null}
              onRefresh={() => void datasetsQuery.refetch()}
              onOpen={openDatabase}
            />
          </Col>
        </Row>
      ),
    },
    {
      key: 'operations',
      // 来源与任务：把外部接口和调度运行态放在一起看。
      label: `来源与任务${alerts.length ? ` ${alerts.length}` : ''}`,
      children: (
        <Row gutter={[14, 14]} className="overview-diagnostic-grid" align="stretch">
          <Col span={8}>
            <SourceHealthPanel
              sources={sources}
              loading={dataSourcesQuery.isLoading || dataSourcesQuery.isFetching}
              error={dataSourcesQuery.isError ? dataSourcesQuery.error : null}
              onRefresh={() => void dataSourcesQuery.refetch()}
              onOpen={openSources}
            />
          </Col>
          <Col span={8}>
            <WorkbenchAlertsPanel
              alerts={alerts}
              loading={
                dataSourcesQuery.isFetching ||
                tasksQuery.isFetching ||
                integrationOverviewQuery.isFetching ||
                databaseStatusQuery.isFetching ||
                qualityOverviewQuery.isFetching
              }
              error={
                dataSourcesQuery.isError ||
                tasksQuery.isError ||
                integrationOverviewQuery.isError ||
                databaseStatusQuery.isError ||
                qualityOverviewQuery.isError
                  ? new Error('overview unavailable')
                  : null
              }
              onRefresh={refreshOverview}
              onOpen={openDatabase}
            />
          </Col>
          <Col span={8}>
            <RecentTaskPanel
              tasks={tasks}
              loading={tasksQuery.isLoading || tasksQuery.isFetching}
              error={tasksQuery.isError ? tasksQuery.error : null}
              onRefresh={() => void tasksQuery.refetch()}
              onOpen={openTasks}
            />
          </Col>
        </Row>
      ),
    },
    {
      key: 'storage',
      // 质量与存储：把问题定位到数据质量或底层存储。
      label: '质量与存储',
      children: (
        <Row gutter={[14, 14]} className="overview-diagnostic-grid" align="stretch">
          <Col span={12}>{qualityRiskPanel}</Col>
          <Col span={12}>{storagePanel}</Col>
        </Row>
      ),
    },
  ];

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }

      // 首屏和诊断区都做轻量淡入，保持管理台的克制动效。
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.045, y: 8 });
      fadeInUp(root.querySelectorAll('.overview-panel'), { delay: 0.08, stagger: 0.04, y: 10 });
    },
    { scope: pageRef },
  );

  return (
    <div className="workbench overview-page" ref={pageRef}>
      {/* 页面标题：只保留最必要的入口，不做解释型首屏。 */}
      <div className="workbench-heading overview-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>数据总控台</Typography.Title>
          <Typography.Text type="secondary">先看结论，再去处理数据源、数值和任务。</Typography.Text>
        </Space>
        <Space className="overview-quick-actions" wrap>
          <Button icon={<ReloadOutlined />} onClick={refreshOverview}>
            刷新状态
          </Button>
          <Button icon={<SyncOutlined />} loading={syncStocksMutation.isPending} onClick={handleSyncStocks}>
            更新股票池
          </Button>
          <Button type="primary" icon={<FileSearchOutlined />} onClick={openNumericSummary}>
            数值汇总
          </Button>
        </Space>
      </div>

      {/* 当前结论：把今天最该先处理的事情压缩成一个动作。 */}
      <section className={`overview-command-board is-${decisionTone}`}>
        <div className="overview-decision-card">
          <div>
            <Space className="overview-decision-label" size={8}>
              <SafetyCertificateOutlined />
            <Typography.Text strong>当前结论</Typography.Text>
            <Tag color={decisionTone === 'success' ? 'green' : decisionTone === 'danger' ? 'red' : 'warning'}>
              {decisionTone === 'success' ? '可用' : decisionTone === 'danger' ? '需处理' : '优先处理'}
            </Tag>
          </Space>
            <Typography.Title level={4}>{decisionTitle}</Typography.Title>
            <Typography.Text type="secondary">{decisionDescription}</Typography.Text>
          </div>
          <Space wrap>
            <Button type="primary" icon={<RightOutlined />} onClick={handleDecisionAction}>
              {decisionActionLabel}
            </Button>
            <Button icon={<FileSearchOutlined />} loading={dailySyncNavigationLoading} disabled={dailySyncNavigationLoading} onClick={openDailySync}>
              {shouldOpenMarketDailyRepair ? '补齐日线缺口' : '日线同步'}
            </Button>
          </Space>
        </div>

        <div className="overview-action-board">
          <div className="overview-action-board-head">
            <div>
              <Typography.Title level={5}>关键功能清单</Typography.Title>
              <Typography.Text type="secondary">按日常使用顺序列出，先判断数据，再进入对应模块处理。</Typography.Text>
            </div>
            <Tag color="blue">{keyFunctionItems.length} 个入口</Tag>
          </div>

          <div className="overview-action-grid">
            {keyFunctionItems.map((item) => (
              <div className={`overview-action-tile ${item.primary ? 'is-primary' : ''}`} key={item.key}>
                <div className="overview-action-head">
                  <span className="overview-action-icon">{item.icon}</span>
                  <Tag color={item.statusColor}>{item.statusLabel}</Tag>
                </div>
                <div className="overview-action-copy">
                  <Typography.Text className="overview-action-role">{item.role}</Typography.Text>
                  <Typography.Title level={5}>{item.title}</Typography.Title>
                  <Typography.Text type="secondary">{item.description}</Typography.Text>
                </div>
                <div className="overview-action-footer">
                  <Typography.Text className="overview-action-metric">{item.metric}</Typography.Text>
                  <Button
                    type={item.primary ? 'primary' : 'default'}
                    size="small"
                    icon={<RightOutlined />}
                    loading={item.actionLoading}
                    disabled={item.actionDisabled}
                    onClick={item.onClick}
                  >
                    {item.actionLabel}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 状态条：用最少的数字给出股票池、日线、源健康和容量四个信号。 */}
      <div className="motion-summary-card overview-status-strip">
        <div>
          <DatabaseOutlined />
          <span>A 股股票池</span>
          <strong>{stocksQuery.isLoading ? '加载中' : `${formatNumber(stocksQuery.data?.total ?? 0)} 只`}</strong>
        </div>
        <div>
          <FileSearchOutlined />
          <span>日线最新日期</span>
          <strong>{integrationOverviewQuery.isLoading ? '加载中' : latestDailyDate ? formatDate(latestDailyDate) : '暂无'}</strong>
          <small>完整度 {coveragePercent}%</small>
        </div>
        <div>
          <ApiOutlined />
          <span>数据源健康</span>
          <strong>{dataSourcesQuery.isLoading ? '加载中' : `${sourceSummary.healthy}/${sources.length}`}</strong>
          <small>{sourceSummary.unhealthy} 个需处理</small>
        </div>
        <div>
          <DatabaseOutlined />
          <span>数据库容量</span>
          <strong>
            {databaseStatusQuery.isLoading
              ? '加载中'
              : formatBytes((databaseStatus?.database_size_bytes ?? 0) + (databaseStatus?.data_lake_size_bytes ?? 0))}
          </strong>
          <small>Parquet {formatNumber(databaseStatus?.parquet_file_count ?? 0)} 个</small>
        </div>
      </div>

      {/* 详细诊断：默认聚焦数值链路，其他模块按需展开。 */}
      <section className="overview-diagnostics-shell">
        <div className="overview-diagnostics-heading">
          <div>
            <Typography.Title level={4}>详细诊断</Typography.Title>
            <Typography.Text type="secondary">默认只展开数值链路；来源、任务、质量和存储作为排障时再看。</Typography.Text>
          </div>
          <Button icon={<RightOutlined />} onClick={openNumericSummary}>
            打开完整数值汇总
          </Button>
        </div>
        <Tabs className="overview-diagnostics-tabs" defaultActiveKey="numeric" items={diagnosticsTabs} />
      </section>
    </div>
  );
}
