import { useMemo, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { App as AntApp, Button, Space, Typography } from 'antd';
import {
  ApiOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import { useDatabaseIntegrationOverviewQuery, useDatabaseStatusQuery } from '../../../features/database/api';
import { useDataQualityOverviewQuery } from '../../../features/data-quality/api';
import { useDatasetsQuery } from '../../../features/datasets/api';
import { useStocksQuery, useSyncStocksMutation } from '../../../features/stocks/api';
import { useSyncTasksQuery } from '../../../features/sync-tasks/api';
import { formatBytes, formatDate, formatNumber } from '../../../shared/components/formatters';
import { formatTaskType } from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';
import { StatusSummaryCard } from './StatusSummaryCard';
import { PipelineFlowCard } from './PipelineFlowCard';
import { QuickActions } from './QuickActions';
import type { AlertItem } from './AlertBanner';

const FIRST_PAGE = 1;
const STOCKS_PREVIEW_SIZE = 5;
const DATASETS_PREVIEW_SIZE = 6;
const TASKS_PREVIEW_SIZE = 6;

function getLatestRecentBatch(batches: { finished_at?: string | null; started_at?: string | null; id: number; status: string; quality_status?: string; dataset_name: string; start_date?: string | null; end_date?: string | null; source?: string; requested_source?: string; records_written: number; schema_version?: number; normalize_version?: number; task_id?: number }[]) {
  if (!batches.length) return undefined;
  return [...batches].sort((left, right) => {
    const lv = left.finished_at ?? left.started_at;
    const rv = right.finished_at ?? right.started_at;
    const lt = lv ? Date.parse(lv) : Number.NaN;
    const rt = rv ? Date.parse(rv) : Number.NaN;
    return (Number.isFinite(rt) ? rt : 0) - (Number.isFinite(lt) ? lt : 0);
  })[0];
}

function getLatestDailyWatermark(watermarks: { dataset_name: string; last_success_at?: string | null; latest_success_date?: string | null; source?: string; requested_source?: string; quality_status?: string; repair_reason?: string | null; symbol?: string | null; repair_start_date?: string | null; repair_end_date?: string | null; market?: string | null }[]) {
  return watermarks
    .filter((w) => w.dataset_name === 'daily_bars')
    .sort((left, right) => {
      const lv = left.last_success_at ?? left.latest_success_date;
      const rv = right.last_success_at ?? right.latest_success_date;
      const lt = lv ? Date.parse(lv) : Number.NaN;
      const rt = rv ? Date.parse(rv) : Number.NaN;
      return (Number.isFinite(rt) ? rt : 0) - (Number.isFinite(lt) ? lt : 0);
    })[0];
}

function buildAlerts({
  sources,
  tasks,
  failedBatches,
  qualityErrorCount,
  dataLakeSize,
}: {
  sources: { health_status: string; name: string }[];
  tasks: { status: string; id: string | number; task_type?: string; taskType?: string }[];
  failedBatches: { id: string | number; dataset_name: string }[];
  qualityErrorCount: number;
  dataLakeSize?: number | null;
}): AlertItem[] {
  const alerts: AlertItem[] = [];
  const unhealthySources = sources.filter(
    (s) => s.health_status === 'unhealthy' || s.health_status === 'unavailable',
  );
  const failedTasks = tasks.filter((t) => t.status === 'failed');

  if (unhealthySources.length > 0) {
    alerts.push({
      key: 'sources',
      title: `${unhealthySources.length} 个数据源需关注`,
      description: unhealthySources.map((s) => s.name).join('、'),
      status: 'warning',
    });
  }

  if (failedTasks.length > 0) {
    alerts.push({
      key: 'tasks',
      title: `最近同步失败 ${failedTasks.length} 个`,
      description: failedTasks
        .slice(0, 3)
        .map((t) => `#${t.id} ${formatTaskType(t.task_type ?? t.taskType ?? 'sync')}`)
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
        .map((b) => `#${b.id} ${formatTaskType(b.dataset_name)}`)
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

export function DataSystemOverviewPage() {
  const { message } = AntApp.useApp();
  const navigate = useNavigate();
  const pageRef = useRef<HTMLDivElement>(null);

  const stocksQuery = useStocksQuery({ market: 'A_SHARE', page: FIRST_PAGE, pageSize: STOCKS_PREVIEW_SIZE });
  const dataSourcesQuery = useDataSourcesQuery();
  const datasetsQuery = useDatasetsQuery({ page: FIRST_PAGE, pageSize: DATASETS_PREVIEW_SIZE });
  const databaseStatusQuery = useDatabaseStatusQuery();
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: 'A_SHARE' });
  const qualityOverviewQuery = useDataQualityOverviewQuery();
  const tasksQuery = useSyncTasksQuery({ page: FIRST_PAGE, pageSize: TASKS_PREVIEW_SIZE });
  const syncStocksMutation = useSyncStocksMutation();

  const sources = dataSourcesQuery.data ?? [];
  const datasets = datasetsQuery.data?.items ?? [];
  const tasks = tasksQuery.data?.items ?? [];
  const overview = qualityOverviewQuery.data;
  const databaseStatus = databaseStatusQuery.data;
  const integrationOverview = integrationOverviewQuery.data;
  const integrationSummary = integrationOverview?.summary;
  const coverageSummary = integrationOverview?.coverage_summary;

  const latestDailyWatermark = useMemo(
    () => getLatestDailyWatermark(integrationOverview?.sync_watermarks ?? []),
    [integrationOverview?.sync_watermarks],
  );

  const dailyMissingSymbolDays = coverageSummary?.daily_missing_symbol_days ?? 0;
  const hasDailyCoverageGap = dailyMissingSymbolDays > 0;
  const sourceUnhealthy = sources.filter(
    (s) => s.health_status === 'unhealthy' || s.health_status === 'unavailable',
  ).length;
  const hasSourceIssue = sourceUnhealthy > 0;
  const failedTaskCount = tasks.filter((t) => t.status === 'failed').length;
  const failedBatchCount = (integrationOverview?.recent_batches ?? []).filter((b) => b.status === 'failed').length;
  const hasExecutionIssue = failedTaskCount > 0 || failedBatchCount > 0 || (overview?.reports_error ?? 0) > 0;

  const decisionTone: 'success' | 'warning' | 'danger' = hasExecutionIssue
    ? 'danger'
    : hasDailyCoverageGap || hasSourceIssue
      ? 'warning'
      : 'success';
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
      ? `${sourceUnhealthy} 个数据源不可用或不健康，先检查鉴权、安装和上游限制。`
      : hasExecutionIssue
        ? `最近失败任务 ${formatNumber(failedTaskCount)} 个，质量错误 ${formatNumber(overview?.reports_error ?? 0)} 条。`
        : '股票池、新闻汇总、数值数据、数据源管理、同步调度和数据库管理都处于可用状态，可以直接继续查看。';

  const openStocks = () => void navigate({ to: '/stocks' });
  const openNumericSummary = () => void navigate({ to: '/data-system/numeric-summary' });
  const openSources = () => void navigate({ to: '/data-system/data-sources' });
  const openDatabase = () => void navigate({ to: '/database' });

  const openDailySync = () => {
    void navigate({
      to: '/sync-tasks',
      search: {
        focus: hasDailyCoverageGap ? 'daily-bars-market-repair' : 'daily-bars',
        market: coverageSummary?.market ?? undefined,
      },
    });
  };

  const refreshOverview = () => {
    void stocksQuery.refetch();
    void dataSourcesQuery.refetch();
    void datasetsQuery.refetch();
    void databaseStatusQuery.refetch();
    void integrationOverviewQuery.refetch();
    void qualityOverviewQuery.refetch();
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

  const alerts = useMemo(
    () =>
      buildAlerts({
        sources,
        tasks,
        failedBatches: integrationOverview?.recent_batches?.filter((b) => b.status === 'failed') ?? [],
        qualityErrorCount: overview?.reports_error ?? 0,
        dataLakeSize: databaseStatus?.data_lake_size_bytes,
      }),
    [databaseStatus?.data_lake_size_bytes, integrationOverview?.recent_batches, overview?.reports_error, sources, tasks],
  );

  const sourceHealthy = sources.filter((s) => s.health_status === 'healthy').length;
  const latestDailyDate = integrationSummary?.latest_data_date;
  const coveragePercent =
    coverageSummary?.daily_completeness != null
      ? Math.round(coverageSummary.daily_completeness * 100)
      : 0;
  const datasetTotalRows = integrationSummary?.total_rows ?? 0;
  const dailySyncLoading = integrationOverviewQuery.isLoading || integrationOverviewQuery.isFetching;

  const handleDecisionAction = hasSourceIssue
    ? openSources
    : hasExecutionIssue
      ? openDatabase
      : openNumericSummary;

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) return;
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.045, y: 8 });
      fadeInUp(root.querySelectorAll('.overview-panel'), { delay: 0.08, stagger: 0.04, y: 10 });
    },
    { scope: pageRef },
  );

  return (
    <div className="workbench overview-page" ref={pageRef}>
      <div className="workbench-heading overview-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>数据总控台</Typography.Title>
          <Typography.Text type="secondary">先看结论，再去处理数据源、数值和任务。</Typography.Text>
        </Space>
        <QuickActions
          onRefresh={refreshOverview}
          onSyncStocks={handleSyncStocks}
          syncLoading={syncStocksMutation.isPending}
          onOpenNumericSummary={openNumericSummary}
          onOpenStocks={openStocks}
        />
      </div>

      <StatusSummaryCard
        decisionTone={decisionTone}
        decisionTitle={decisionTitle}
        decisionDescription={decisionDescription}
        decisionActionLabel={
          hasSourceIssue ? '检查数据源' : hasExecutionIssue ? '查看数据库状态' : '查看数值汇总'
        }
        onDecisionAction={handleDecisionAction}
        dailySyncLabel={hasDailyCoverageGap ? '补齐日线缺口' : '日线同步'}
        onDailySync={openDailySync}
        dailySyncLoading={dailySyncLoading}
        alerts={alerts}
      />

      <div className="motion-summary-card overview-status-strip">
        <div>
          <DatabaseOutlined />
          <span>A 股股票池</span>
          <strong>{stocksQuery.isLoading ? '加载中' : `${formatNumber(stocksQuery.data?.total ?? 0)} 只`}</strong>
        </div>
        <div>
          <FileSearchOutlined />
          <span>日线最新日期</span>
          <strong>
            {integrationOverviewQuery.isLoading ? '加载中' : latestDailyDate ? formatDate(latestDailyDate) : '暂无'}
          </strong>
          <small>完整度 {coveragePercent}%</small>
        </div>
        <div>
          <ApiOutlined />
          <span>数据源健康</span>
          <strong>{dataSourcesQuery.isLoading ? '加载中' : `${sourceHealthy}/${sources.length}`}</strong>
          <small>{sourceUnhealthy} 个需处理</small>
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

      <PipelineFlowCard
        sourceHealthy={sourceHealthy}
        sourceTotal={sources.length}
        sourceUnhealthy={sourceUnhealthy}
        dailyMissingSymbolDays={dailyMissingSymbolDays}
        latestDailyDate={latestDailyDate ? formatDate(latestDailyDate) : null}
        coveragePercent={coveragePercent}
        datasetCount={integrationSummary?.datasets_total ?? datasetsQuery.data?.total ?? 0}
        datasetTotalRows={datasetTotalRows}
        onOpenSources={openSources}
        onOpenDatabase={openDatabase}
        onOpenNumericSummary={openNumericSummary}
        onOpenStocks={openStocks}
      />
    </div>
  );
}
