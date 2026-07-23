import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import {
  CalendarOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  ProfileOutlined,
  ReloadOutlined,
  StockOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import {
  useDataQualityCheckRunsQuery,
  useDataQualityOverviewQuery,
  useDataQualityReportsQuery,
  useRunDataQualityCheckMutation,
} from '../../../features/data-quality/api';
import type { DataQualityReport, DataQualityReportListParams } from '../../../features/data-quality/types';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import type {
  DataSource,
  DataSourceCapability,
  DataSourceProviderMetadata,
  DataSourceSmokeSummary,
} from '../../../features/data-sources/types';
import { useDatabaseIntegrationOverviewQuery, useDatabaseLineageQuery, useDatabaseStatusQuery } from '../../../features/database/api';
import type {
  DatabaseCoverageSummary,
  DatabaseIntegrationOverview,
  DatabaseLineageItem,
  DatabaseLineageParams,
  DatasetSnapshot,
  ProviderIntegration,
  RecentIngestBatch,
  SyncWatermark,
} from '../../../features/database/types';
import { useDatasetsQuery } from '../../../features/datasets/api';
import type { Dataset } from '../../../features/datasets/types';
import { useTradingCalendarsQuery } from '../../../features/trading-calendars/api';
import type { TradingCalendarDay } from '../../../features/trading-calendars/types';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatBytes, formatDate, formatDateTime, formatNumber, formatPercent } from '../../../shared/components/formatters';
import {
  formatCapability,
  formatAuthMode,
  formatExchange,
  formatLayer,
  formatMarket,
  formatProviderType,
  formatQualityCheckType,
  formatStability,
  formatStorageType,
  formatTaskType,
  aShareMarketOptions,
} from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

// ── Extracted sub-modules ──
import {
  FIRST_PAGE,
  DATASET_PAGE_SIZE,
  CALENDAR_PAGE_SIZE,
  REPORT_PAGE_SIZE,
  LINEAGE_PAGE_SIZE,
  DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
  DEFAULT_MARKET,
  V1_DATA_SOURCE_CODES,
  databaseMarketOptions,
  lineageDatasetOptions,
  lineageStatusOptions,
  qualityStatusOptions,
  qualitySeverityOptions,
  type DatasetMetricSource,
  type FreshnessDatasetName,
  type FreshnessItem,
  type RepairSearch,
  type QualityAction,
  type CalendarCoverageStats,
  type LineageFilterValues,
  type TraceQualityReportBatch,
  getLatestDatasetDate,
  getDatasetStorageSummary,
  getDatasetRowsTotal,
  getDatasetSnapshotByName,
  getSourceCapabilities,
  getSourceMetadata,
  getSourceLastSmoke,
  formatSourceHealthMessage,
  formatCapabilitySummary,
  formatDailyBarExchanges,
  formatSmokeSample,
  getDateRange,
  getCalendarCoverageStats,
  getDatasetFreshnessItems,
  getFreshnessTagColor,
  getMetadataStoreLabel,
  formatRange,
  formatWatermarkScope,
  formatRepairRange,
  getDailyCompletenessPercent,
  isCoverageDegraded,
  findRepairableDailyWatermark,
  isMarketDailyRepairHint,
  getMarketRepairSearch,
  getQualityReportAction,
  getClosedLoopStatus,
  getRepairFocus,
  getRepairSearch,
  formatDatabaseRole,
  formatDuckDbEngineStatus,
  getDuckDbEngineStatusColor,
  getNumericRecordId,
  getNumericTaskId,
  scrollToLineageSection,
} from './components/utils';
import {
  buildDatasetColumns,
  buildSnapshotColumns,
  buildWatermarkColumns,
  buildProviderColumns,
  buildProviderStatusColumns,
  buildBatchColumns,
  buildLineageColumns,
  buildReportColumns,
} from './components/columns';
import {
  DataClosedLoopPanel,
  CoverageSummaryPanel,
  DataFreshnessPanel,
} from './components/panels';

export function DatabaseManagementPage() {
  const { message } = AntApp.useApp();
  const pageRef = useRef<HTMLDivElement>(null);
  const search = useSearch({ from: '/database' });
  const navigate = useNavigate({ from: '/database' });
  const hasLineageFilters = Boolean(
    search.lineageBatchId ||
      search.lineageDatasetName ||
      search.lineageSymbol ||
      search.lineageTradeDate ||
      search.lineageSource ||
      search.lineageStatus,
  );
  const hasQualityFilters = Boolean(
    search.qualityDatasetName || search.qualityStatus || search.qualitySeverity || search.qualityCheckedAt,
  );
  const shouldOpenCalendar = search.view === 'calendar';
  const shouldOpenQuality = search.view === 'quality' || hasQualityFilters;
  const [lineageEnabled, setLineageEnabled] = useState(hasLineageFilters);
  const [calendarEnabled, setCalendarEnabled] = useState(shouldOpenCalendar);
  const [qualityEnabled, setQualityEnabled] = useState(shouldOpenQuality);
  const selectedMarket = search.market || DEFAULT_MARKET;
  useEffect(() => {
    if (hasLineageFilters) {
      setLineageEnabled(true);
    }
  }, [hasLineageFilters]);
  useEffect(() => {
    if (shouldOpenCalendar) {
      setCalendarEnabled(true);
      window.requestAnimationFrame(() => document.querySelector('#database-calendar-section')?.scrollIntoView({ block: 'start' }));
    }
  }, [shouldOpenCalendar]);
  useEffect(() => {
    if (shouldOpenQuality) {
      setQualityEnabled(true);
      window.requestAnimationFrame(() => document.querySelector('#database-quality-section')?.scrollIntoView({ block: 'start' }));
    }
  }, [shouldOpenQuality]);
  const qualityParams = useMemo<DataQualityReportListParams>(
    () => ({
      datasetName: search.qualityDatasetName ?? '',
      status: search.qualityStatus ?? '',
      severity: search.qualitySeverity ?? '',
      checkedAt: search.qualityCheckedAt ?? '',
      page: search.qualityPage ?? FIRST_PAGE,
      pageSize: search.qualityPageSize ?? REPORT_PAGE_SIZE,
    }),
    [
      search.qualityCheckedAt,
      search.qualityDatasetName,
      search.qualityPage,
      search.qualityPageSize,
      search.qualitySeverity,
      search.qualityStatus,
    ],
  );
  const lineageParams = useMemo<DatabaseLineageParams>(
    () => ({
      batchId: search.lineageBatchId,
      datasetName: search.lineageDatasetName ?? '',
      market: selectedMarket,
      symbol: search.lineageSymbol ?? '',
      tradeDate: search.lineageTradeDate ?? '',
      source: search.lineageSource ?? '',
      status: search.lineageStatus ?? '',
      page: search.lineagePage ?? FIRST_PAGE,
      pageSize: search.lineagePageSize ?? LINEAGE_PAGE_SIZE,
    }),
    [
      search.lineageBatchId,
      search.lineageDatasetName,
      search.lineagePage,
      search.lineagePageSize,
      search.lineageSource,
      search.lineageStatus,
      search.lineageSymbol,
      search.lineageTradeDate,
      selectedMarket,
    ],
  );
  const datasetsQuery = useDatasetsQuery({ page: FIRST_PAGE, pageSize: DATASET_PAGE_SIZE });
  const databaseStatusQuery = useDatabaseStatusQuery();
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: selectedMarket });
  const lineageQuery = useDatabaseLineageQuery(lineageParams, { enabled: lineageEnabled });
  const calendarsQuery = useTradingCalendarsQuery({
    market: selectedMarket,
    page: FIRST_PAGE,
    pageSize: CALENDAR_PAGE_SIZE,
  }, { enabled: calendarEnabled });
  const dataSourcesQuery = useDataSourcesQuery();
  const qualityOverviewQuery = useDataQualityOverviewQuery();
  const qualityCheckRunsQuery = useDataQualityCheckRunsQuery({ enabled: qualityEnabled });
  const qualityReportsQuery = useDataQualityReportsQuery(qualityParams, { enabled: qualityEnabled });
  const qualityCheckMutation = useRunDataQualityCheckMutation();

  const datasets = datasetsQuery.data?.items ?? [];
  const calendars = calendarsQuery.data?.items ?? [];
  const dataSources = useMemo(
    () => (dataSourcesQuery.data ?? []).filter((source) => V1_DATA_SOURCE_CODES.has(source.code)),
    [dataSourcesQuery.data],
  );
  const reports = qualityReportsQuery.data?.items ?? [];
  const qualityCheckRuns = qualityCheckRunsQuery.data ?? [];
  const lineageItems = lineageQuery.data?.items ?? [];
  const databaseStatus = databaseStatusQuery.data;
  const qualityOverview = qualityOverviewQuery.data;
  const integrationOverview = integrationOverviewQuery.data;
  const coverageSummary = integrationOverview?.coverage_summary;
  const datasetSnapshots = integrationOverview?.dataset_snapshots ?? [];
  const datasetColumns = useMemo(() => buildDatasetColumns(), []);
  const snapshotColumns = useMemo(() => buildSnapshotColumns(), []);
  const watermarkColumns = useMemo(() => buildWatermarkColumns(coverageSummary), [coverageSummary]);
  const providerColumns = useMemo(() => buildProviderColumns(), []);
  const providerStatusColumns = useMemo(() => buildProviderStatusColumns(), []);
  const lineageColumns = useMemo(() => buildLineageColumns(), []);
  const storageMetricSource = useMemo(
    () => (datasetSnapshots.length > 0 ? datasetSnapshots : datasets),
    [datasetSnapshots, datasets],
  );
  const storageSummary = useMemo(() => getDatasetStorageSummary(storageMetricSource), [storageMetricSource]);
  const latestDatasetDate = getLatestDatasetDate(storageMetricSource);
  const dailyBarsSnapshot = getDatasetSnapshotByName(datasetSnapshots, 'daily_bars');
  const tradingCalendarSnapshot = getDatasetSnapshotByName(datasetSnapshots, 'trading_calendars');
  const latestCalendarDate = calendars[0]?.trade_date;
  const calendarCoverageStats = useMemo(
    () => getCalendarCoverageStats(calendars, coverageSummary, tradingCalendarSnapshot),
    [calendars, coverageSummary, tradingCalendarSnapshot],
  );
  const totalRows = getDatasetRowsTotal(storageMetricSource);
  const integrationSummary = integrationOverview?.summary;
  const datasetsTotal = integrationSummary?.datasets_total ?? datasetsQuery.data?.total ?? 0;
  const rowsTotal = integrationSummary?.total_rows ?? totalRows;
  const qualityRunOptions = useMemo(
    () => [
      { label: '最新检查批次', value: '' },
      ...qualityCheckRuns.map((run) => ({
        label: `${formatDateTime(run.checked_at)} / ${formatNumber(run.reports_total)} 条`,
        value: run.checked_at,
      })),
    ],
    [qualityCheckRuns],
  );

  const traceRecentBatch = useCallback(
    (batch: RecentIngestBatch) => {
      void navigate({
        search: {
          ...search,
          lineageBatchId: Number(batch.id),
          lineageDatasetName: batch.dataset_name,
          lineageSymbol: batch.symbol ?? undefined,
          lineageTradeDate: batch.end_date ?? batch.start_date ?? undefined,
          lineageSource: batch.source,
          lineageStatus: batch.status,
          lineagePage: FIRST_PAGE,
          lineagePageSize: lineageParams.pageSize,
        },
      });
      scrollToLineageSection();
    },
    [lineageParams.pageSize, navigate, search],
  );

  const traceQualityReportBatch = useCallback(
    (report: DataQualityReport) => {
      const trace = report.trace;
      const batchId = getNumericRecordId(trace?.latest_batch_id);
      if (!trace || !batchId) {
        return;
      }

      void navigate({
        search: {
          ...search,
          market: trace.latest_batch_market || search.market || selectedMarket,
          lineageBatchId: batchId,
          lineageDatasetName: report.dataset_name,
          lineageSymbol: trace.latest_batch_symbol ?? undefined,
          lineageTradeDate: trace.latest_batch_end_date ?? trace.latest_batch_start_date ?? undefined,
          lineageSource: trace.latest_batch_source || trace.dataset_source || undefined,
          lineageStatus: trace.latest_batch_status || undefined,
          lineagePage: FIRST_PAGE,
          lineagePageSize: lineageParams.pageSize,
        },
      });
      scrollToLineageSection();
    },
    [lineageParams.pageSize, navigate, search, selectedMarket],
  );

  const reportColumns = useMemo(
    () => buildReportColumns(coverageSummary, traceQualityReportBatch),
    [coverageSummary, traceQualityReportBatch],
  );
  const batchColumns = useMemo(() => buildBatchColumns(traceRecentBatch), [traceRecentBatch]);

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.05, y: 8 });
      fadeInUp(root.querySelectorAll('.database-panel'), { delay: 0.08, stagger: 0.04, y: 10 });
    },
    { scope: pageRef },
  );

  const refreshAll = () => {
    void datasetsQuery.refetch();
    void databaseStatusQuery.refetch();
    void integrationOverviewQuery.refetch();
    void dataSourcesQuery.refetch();
    void qualityOverviewQuery.refetch();
    if (lineageEnabled) {
      void lineageQuery.refetch();
    }
    if (calendarEnabled) {
      void calendarsQuery.refetch();
    }
    if (qualityEnabled) {
      void qualityCheckRunsQuery.refetch();
      void qualityReportsQuery.refetch();
    }
  };

  const runQualityCheck = () => {
    qualityCheckMutation.mutate(undefined, {
      onSuccess: (result) => {
        void message.success(`已检查 ${result.checked_datasets} 个数据集，生成 ${result.reports_created} 条质量报告`);
        void qualityOverviewQuery.refetch();
        void qualityCheckRunsQuery.refetch();
        void qualityReportsQuery.refetch();
        void integrationOverviewQuery.refetch();
        void datasetsQuery.refetch();
      },
      onError: (error) => {
        void message.error(error instanceof Error ? error.message : '数据质量检查执行失败');
      },
    });
  };

  return (
    <div className="workbench database-page" ref={pageRef}>
      <div className="workbench-heading database-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>存储引擎管理</Typography.Title>
          <Typography.Text type="secondary">
            看行情热库、Parquet 数据湖、DuckDB 查询和元数据目录的分工与状态
          </Typography.Text>
        </Space>
        <Space wrap className="database-heading-actions">
          <Select
            className="database-market-select"
            value={selectedMarket}
            options={databaseMarketOptions}
            onChange={(market) => {
              void navigate({
                search: {
                  ...search,
                  market,
                  qualityPage: FIRST_PAGE,
                  lineagePage: FIRST_PAGE,
                },
              });
            }}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={refreshAll}
            loading={
              datasetsQuery.isFetching ||
              databaseStatusQuery.isFetching ||
              integrationOverviewQuery.isFetching ||
              dataSourcesQuery.isFetching ||
              lineageQuery.isFetching ||
              calendarsQuery.isFetching ||
              qualityOverviewQuery.isFetching ||
              qualityReportsQuery.isFetching
            }
          >
            刷新状态
          </Button>
        </Space>
      </div>

      <DataClosedLoopPanel
        overview={integrationOverview}
        loading={integrationOverviewQuery.isLoading}
        error={integrationOverviewQuery.isError}
      />

      <Row gutter={[16, 16]} className="summary-row database-status-row">
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="元数据目录"
              value={getMetadataStoreLabel(databaseStatus?.database_kind)}
              prefix={<DatabaseOutlined />}
              loading={databaseStatusQuery.isLoading}
            />
            <Typography.Text type="secondary">
              {formatDatabaseRole(databaseStatus?.database_role)} / 本地文件容量 {formatBytes(databaseStatus?.database_size_bytes)}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="Parquet 冷湖"
              value={formatBytes(databaseStatus?.data_lake_size_bytes)}
              prefix={<FileSearchOutlined />}
              loading={databaseStatusQuery.isLoading}
            />
            <Typography.Text type="secondary">
              Parquet {formatNumber(databaseStatus?.parquet_file_count ?? 0)} / 文件{' '}
              {formatNumber(databaseStatus?.total_file_count ?? 0)}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="日线最新数据日"
              value={formatDate(dailyBarsSnapshot?.latest_data_date ?? integrationSummary?.latest_data_date ?? latestDatasetDate)}
              prefix={<CalendarOutlined />}
              loading={datasetsQuery.isLoading || integrationOverviewQuery.isLoading}
            />
            <Typography.Text type="secondary">
              交易日历到 {latestCalendarDate ? formatDate(latestCalendarDate) : '-'}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="motion-summary-card">
            <Statistic
              title="质量错误"
              value={qualityOverview?.reports_error ?? 0}
              suffix="条"
              prefix={<SafetyCertificateOutlined />}
              loading={qualityOverviewQuery.isLoading}
            />
            <Typography.Text type="secondary">
              通过 {formatNumber(qualityOverview?.datasets_good ?? 0)} / 总计{' '}
              {formatNumber(qualityOverview?.datasets_total ?? 0)}
            </Typography.Text>
          </Card>
        </Col>
      </Row>

      <div className="database-section-nav">
        <a href="#database-coverage-section">覆盖</a>
        <a href="#database-storage-section">引擎</a>
        <a href="#database-providers-section">数据源</a>
        <a href="#database-freshness-section">新鲜度</a>
        <a href="#database-lineage-section">批次追溯</a>
        <a href="#database-datasets-section">目录</a>
        <a href="#database-quality-section">质量</a>
      </div>

      <Row id="database-storage-section" gutter={[16, 16]} className="database-storage-row">
        <Col xs={24} xl={12}>
          <Card className="database-panel database-storage-card" title="存储引擎分工">
            {databaseStatusQuery.isError ? (
              <Alert type="error" showIcon message="存储状态加载失败" />
            ) : databaseStatusQuery.isLoading ? (
              <Skeleton active paragraph={{ rows: 3 }} />
            ) : (
              <Space direction="vertical" size={8}>
                <Alert
                  type={databaseStatus?.database_role === 'local_fallback' ? 'info' : 'success'}
                  showIcon
                  message={databaseStatus?.database_note}
                />
                <div className="database-storage-map">
                  <div>
                    <Typography.Text strong>行情热库</Typography.Text>
                    <Typography.Text type="secondary">目标使用 ClickHouse 承接日线、分钟线、因子和高并发筛选查询</Typography.Text>
                    <Space size={[6, 6]} wrap>
                      <Typography.Text code>ClickHouse</Typography.Text>
                      <Tag color="orange">待接入</Tag>
                    </Space>
                  </div>
                  <div>
                    <Typography.Text strong>行情冷湖</Typography.Text>
                    <Typography.Text type="secondary">当前日线等大规模行情数据，以 Parquet 文件保存</Typography.Text>
                    <Typography.Text code>{databaseStatus?.data_lake_path}</Typography.Text>
                  </div>
                  <div>
                    <Typography.Text strong>本地查询引擎</Typography.Text>
                    <Typography.Text type="secondary">DuckDB 负责扫描和聚合 Parquet，不作为主存储库</Typography.Text>
                    <Space size={[6, 6]} wrap>
                      <Typography.Text code>DuckDB / Parquet Reader</Typography.Text>
                      <Tag color={getDuckDbEngineStatusColor(databaseStatus?.duckdb_engine_status)}>
                        {formatDuckDbEngineStatus(databaseStatus?.duckdb_engine_status)}
                      </Tag>
                    </Space>
                    <Typography.Text type="secondary">{databaseStatus?.duckdb_engine_note}</Typography.Text>
                  </div>
                  <div>
                    <Typography.Text strong>元数据目录</Typography.Text>
                    <Typography.Text type="secondary">股票池、数据源、同步任务、批次、目录和质量报告</Typography.Text>
                    <Typography.Text code>{databaseStatus?.database_url}</Typography.Text>
                  </div>
                </div>
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="database-panel database-storage-card" title="当前落地状态">
            <div className="database-storage-summary-grid">
              <div>
                <Typography.Text type="secondary">数据集</Typography.Text>
                <Typography.Title level={4}>{formatNumber(datasetsTotal)} 个</Typography.Title>
              </div>
              <div>
                <Typography.Text type="secondary">行情热库</Typography.Text>
                <Typography.Title level={4}>ClickHouse</Typography.Title>
                <Tag color="orange">下一阶段接入</Tag>
              </div>
              <div>
                <Typography.Text type="secondary">行情文件集</Typography.Text>
                <Typography.Title level={4}>{formatNumber(storageSummary.parquet ?? 0)} 个</Typography.Title>
                <Tag color="blue">Parquet 数据湖</Tag>
              </div>
              <div>
                <Typography.Text type="secondary">查询方式</Typography.Text>
                <Typography.Title level={4}>DuckDB</Typography.Title>
                <Tag color="green">查询引擎，不是主库</Tag>
              </div>
            </div>
            <Typography.Text type="secondary">
              全量目录记录 {formatNumber(rowsTotal)} 行；行情主路径是热库/数据湖，SQLite 只保留本地元数据兜底。
            </Typography.Text>
          </Card>
        </Col>
      </Row>

      <Card id="database-coverage-section" className="database-panel database-coverage-card" title="覆盖率摘要">
        <CoverageSummaryPanel
          coverage={integrationOverview?.coverage_summary}
          loading={integrationOverviewQuery.isLoading}
          error={integrationOverviewQuery.isError}
        />
      </Card>

      <Card id="database-freshness-section" className="database-panel database-freshness-card" title="数据新鲜度">
        <DataFreshnessPanel
          snapshots={datasetSnapshots}
          loading={integrationOverviewQuery.isLoading}
          error={integrationOverviewQuery.isError}
        />
      </Card>

      <Card id="database-lineage-section" className="database-panel database-table-card" title="批次级数据血缘查询">
        <Space className="database-lineage-stack" direction="vertical" size={14}>
          <Alert
            type="info"
            showIcon
            message="按入库批次追溯数据从哪里来、写到了哪里"
            description="这里查询的是 V1 批次级血缘：请求来源、实际来源、任务、schema/normalize 版本、记录数、质量和失败原因；暂不做字段级血缘和复杂 DAG。"
          />
          <Form<LineageFilterValues>
            key={[
              lineageParams.batchId ?? '',
              lineageParams.datasetName,
              lineageParams.symbol,
              lineageParams.tradeDate,
              lineageParams.source,
              lineageParams.status,
            ].join('|')}
            className="stock-filters database-lineage-filters"
            layout="inline"
            initialValues={{
              batchId: lineageParams.batchId,
              datasetName: lineageParams.datasetName,
              symbol: lineageParams.symbol,
              tradeDate: lineageParams.tradeDate ? dayjs(lineageParams.tradeDate) : undefined,
              source: lineageParams.source,
              status: lineageParams.status,
            }}
            onFinish={(values) => {
              setLineageEnabled(true);
              void navigate({
                search: {
                  ...search,
                  lineageBatchId: values.batchId || undefined,
                  lineageDatasetName: values.datasetName || undefined,
                  lineageSymbol: values.symbol?.trim() || undefined,
                  lineageTradeDate: values.tradeDate?.format('YYYY-MM-DD'),
                  lineageSource: values.source?.trim() || undefined,
                  lineageStatus: values.status || undefined,
                  lineagePage: FIRST_PAGE,
                  lineagePageSize: lineageParams.pageSize,
                },
              });
            }}
          >
            <Form.Item label="批次 ID" name="batchId" className="filter-keyword">
              <InputNumber className="full-width-control" min={1} precision={0} placeholder="如 23" />
            </Form.Item>
            <Form.Item label="数据集" name="datasetName">
              <Select className="filter-select-wide" options={lineageDatasetOptions} />
            </Form.Item>
            <Form.Item label="股票代码" name="symbol" className="filter-keyword">
              <Input allowClear placeholder="如 600519" />
            </Form.Item>
            <Form.Item label="交易日" name="tradeDate">
              <DatePicker className="full-width-control" />
            </Form.Item>
            <Form.Item label="来源" name="source" className="filter-keyword">
              <Input allowClear placeholder="如 akshare / adata / stock_sdk" />
            </Form.Item>
            <Form.Item label="状态" name="status">
              <Select className="filter-select" options={lineageStatusOptions} />
            </Form.Item>
            <Form.Item className="filter-actions">
              <Space wrap>
                <Button type="primary" htmlType="submit">
                  查询血缘
                </Button>
                <Button
                  onClick={() => {
                    setLineageEnabled(true);
                    void navigate({
                      search: {
                        ...search,
                        lineageBatchId: undefined,
                        lineageDatasetName: undefined,
                        lineageSymbol: undefined,
                        lineageTradeDate: undefined,
                        lineageSource: undefined,
                        lineageStatus: undefined,
                        lineagePage: FIRST_PAGE,
                        lineagePageSize: lineageParams.pageSize,
                      },
                    });
                  }}
                >
                  重置
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  loading={lineageQuery.isFetching}
                  onClick={() => {
                    if (!lineageEnabled) {
                      setLineageEnabled(true);
                      return;
                    }
                    void lineageQuery.refetch();
                  }}
                >
                  刷新
                </Button>
              </Space>
            </Form.Item>
          </Form>
          {lineageEnabled ? (
            lineageQuery.isError ? (
              <Alert type="error" showIcon message="批次血缘加载失败" description="后端批次血缘接口暂不可用。" />
            ) : (
              <Table<DatabaseLineageItem>
                rowKey={(record) => String(record.id)}
                columns={lineageColumns}
                dataSource={lineageItems}
                loading={lineageQuery.isFetching}
                size="small"
                scroll={{ x: 1420 }}
                locale={{
                  emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无批次级血缘记录" />,
                }}
                pagination={{
                  current: lineageParams.page,
                  pageSize: lineageParams.pageSize,
                  total: lineageQuery.data?.total ?? 0,
                  showSizeChanger: false,
                  showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${formatNumber(total)} 条`,
                  onChange: (page, pageSize) => {
                    void navigate({
                      search: {
                        ...search,
                        lineageBatchId: lineageParams.batchId || undefined,
                        lineageDatasetName: lineageParams.datasetName || undefined,
                        lineageSymbol: lineageParams.symbol || undefined,
                        lineageTradeDate: lineageParams.tradeDate || undefined,
                        lineageSource: lineageParams.source || undefined,
                        lineageStatus: lineageParams.status || undefined,
                        lineagePage: page,
                        lineagePageSize: pageSize,
                      },
                    });
                  },
                }}
              />
            )
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="默认不加载批次血缘。使用筛选或点击“刷新”后再查看。"
            />
          )}
        </Space>
      </Card>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={14}>
          <Card className="database-panel database-table-card" title="数据版本 / 快照">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="数据整合总览加载失败" description="后端整合总览接口暂不可用。" />
            ) : (
              <Table<DatasetSnapshot>
                rowKey={(record) => record.dataset_name}
                columns={snapshotColumns}
                dataSource={datasetSnapshots}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                scroll={{ x: 980 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据集快照" /> }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="database-panel database-table-card" title="同步水位线">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="同步水位线加载失败" />
            ) : (
              <Table<SyncWatermark>
                rowKey={(record) => `${record.dataset_name}-${record.source}-${record.market}-${record.symbol}-${record.batch_id}`}
                columns={watermarkColumns}
                dataSource={integrationOverview?.sync_watermarks ?? []}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 1320 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无成功水位线" /> }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={11}>
          <Card id="database-providers-section" className="database-panel database-table-card" title="Provider 状态与取样">
            {dataSourcesQuery.isError ? (
              <Alert type="error" showIcon message="数据源状态加载失败" description="后端数据源管理接口暂不可用。" />
            ) : (
              <Table<DataSource>
                rowKey={(record) => record.code}
                columns={providerStatusColumns}
                dataSource={dataSources}
                loading={dataSourcesQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 980 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据源状态" /> }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={13}>
          <Card className="database-panel database-table-card" title="数据源整合概况">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="数据源整合概况加载失败" />
            ) : (
              <Table<ProviderIntegration>
                rowKey={(record) => record.source}
                columns={providerColumns}
                dataSource={integrationOverview?.provider_integrations ?? []}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 850 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据源批次" /> }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col span={24}>
          <Card className="database-panel database-table-card" title="最近入库批次（worker 执行结果）">
            {integrationOverviewQuery.isError ? (
              <Alert type="error" showIcon message="最近批次加载失败" />
            ) : (
              <Table<RecentIngestBatch>
                rowKey={(record) => String(record.id)}
                columns={batchColumns}
                dataSource={integrationOverview?.recent_batches ?? []}
                loading={integrationOverviewQuery.isFetching}
                pagination={false}
                size="small"
                scroll={{ x: 1080 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无整合批次" /> }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={16}>
          <Card id="database-datasets-section" className="database-panel database-table-card" title="存放内容">
            {datasetsQuery.isError ? (
              <Alert type="error" showIcon message="数据集加载失败" description="后端数据集接口暂不可用。" />
            ) : (
              <Table<Dataset>
                rowKey={(record) => String(record.id)}
                columns={datasetColumns}
                dataSource={datasets}
                loading={datasetsQuery.isFetching}
                pagination={false}
                scroll={{ x: 1100 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据集" /> }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card id="database-calendar-section" className="database-panel database-calendar-card" title="交易日历覆盖">
            <Space direction="vertical" size={12}>
              <Space wrap>
                <Button
                  type="primary"
                  icon={<CalendarOutlined />}
                  onClick={() => {
                    setCalendarEnabled(true);
                  }}
                >
                  加载交易日历
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  loading={calendarsQuery.isFetching}
                  onClick={() => {
                    if (!calendarEnabled) {
                      setCalendarEnabled(true);
                      return;
                    }
                    void calendarsQuery.refetch();
                  }}
                >
                  刷新
                </Button>
              </Space>
              {calendarEnabled ? (
                calendarsQuery.isError ? (
                  <Alert type="error" showIcon message="交易日历加载失败" />
                ) : calendarsQuery.isLoading || integrationOverviewQuery.isLoading ? (
                  <Skeleton active paragraph={{ rows: 6 }} />
                ) : calendars.length === 0 && !calendarCoverageStats.latestDate ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无交易日历" />
                ) : (
                  <Space className="database-calendar-stack" direction="vertical" size={12}>
                    <div className="database-calendar-summary-grid">
                      <div>
                        <Typography.Text type="secondary">覆盖范围</Typography.Text>
                        <Typography.Title level={5}>
                          {formatRange(calendarCoverageStats.coverageStart, calendarCoverageStats.coverageEnd)}
                        </Typography.Title>
                      </div>
                      <div>
                        <Typography.Text type="secondary">最新日历日期</Typography.Text>
                        <Typography.Title level={5}>{formatDate(calendarCoverageStats.latestDate)}</Typography.Title>
                      </div>
                      <div>
                        <Typography.Text type="secondary">当前样本</Typography.Text>
                        <Typography.Title level={5}>{formatNumber(calendarCoverageStats.loadedTotal)} 天</Typography.Title>
                        <Typography.Text type="secondary">
                          {formatRange(calendarCoverageStats.loadedStart, calendarCoverageStats.loadedEnd)}
                        </Typography.Text>
                      </div>
                      <div>
                        <Typography.Text type="secondary">开市 / 休市</Typography.Text>
                        <Typography.Title level={5}>
                          {formatNumber(calendarCoverageStats.loadedOpenDays)} / {formatNumber(calendarCoverageStats.loadedClosedDays)}
                        </Typography.Title>
                        <Typography.Text type="secondary">按当前已加载样本</Typography.Text>
                      </div>
                    </div>
                    <List
                      className="database-calendar-list"
                      dataSource={calendars}
                      renderItem={(day) => (
                        <List.Item>
                          <Space className="database-calendar-row">
                            <Typography.Text strong>{formatDate(day.trade_date)}</Typography.Text>
                            <Tag color={day.is_open ? 'green' : 'default'}>{day.is_open ? '开市' : '休市'}</Tag>
                            <Typography.Text type="secondary">{formatMarket(day.market)}</Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Space>
                )
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="默认不加载交易日历样本。点击“加载交易日历”后再查看。"
                />
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      <Card id="database-quality-section" className="database-panel database-quality-card" title="质量风险">
        {qualityOverviewQuery.isError ? (
          <Alert type="error" showIcon message="质量信息加载失败" />
        ) : (
          <Space className="database-quality-stack" direction="vertical" size={14}>
            <div className="database-quality-toolbar">
              <Form
                className="stock-filters quality-filters database-quality-filters"
                layout="inline"
                initialValues={{
                  checkedAt: qualityParams.checkedAt,
                  datasetName: qualityParams.datasetName,
                  status: qualityParams.status,
                  severity: qualityParams.severity,
                }}
                onFinish={(values: { checkedAt?: string; datasetName?: string; status?: string; severity?: string }) => {
                  setQualityEnabled(true);
                  void navigate({
                    search: {
                      ...search,
                      qualityCheckedAt: values.checkedAt || undefined,
                      qualityDatasetName: values.datasetName?.trim() || undefined,
                      qualityStatus: values.status || undefined,
                      qualitySeverity: values.severity || undefined,
                      qualityPage: FIRST_PAGE,
                      qualityPageSize: qualityParams.pageSize,
                    },
                  });
                }}
              >
                <Form.Item name="checkedAt">
                  <Select className="filter-select-wide" options={qualityRunOptions} loading={qualityCheckRunsQuery.isFetching} />
                </Form.Item>
                <Form.Item name="datasetName" className="filter-keyword">
                  <Input allowClear placeholder="数据集名称，如 daily_bars" />
                </Form.Item>
                <Form.Item name="status">
                  <Select className="filter-select" options={qualityStatusOptions} />
                </Form.Item>
                <Form.Item name="severity">
                  <Select className="filter-select-wide" options={qualitySeverityOptions} />
                </Form.Item>
                <Form.Item className="filter-actions">
                  <Space wrap>
                    <Button
                      type="primary"
                      htmlType="submit"
                      onClick={() => {
                        setQualityEnabled(true);
                      }}
                    >
                      查询
                    </Button>
                    <Button
                      icon={<ReloadOutlined />}
                      loading={qualityOverviewQuery.isFetching || qualityCheckRunsQuery.isFetching || qualityReportsQuery.isFetching}
                      onClick={() => {
                        void qualityOverviewQuery.refetch();
                        if (!qualityEnabled) {
                          setQualityEnabled(true);
                          return;
                        }
                        void qualityCheckRunsQuery.refetch();
                        void qualityReportsQuery.refetch();
                      }}
                    >
                      刷新
                    </Button>
                    <Button
                      type="primary"
                      icon={<SafetyCertificateOutlined />}
                      loading={qualityCheckMutation.isPending}
                      onClick={() => {
                        setQualityEnabled(true);
                        runQualityCheck();
                      }}
                    >
                      运行检查
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
              <Typography.Text type="secondary">
                当前批次：{formatDateTime(qualityReportsQuery.data?.checked_at ?? qualityParams.checkedAt)}；历史报告总数 {formatNumber(qualityOverview?.reports_total ?? 0)}
              </Typography.Text>
            </div>
            {qualityEnabled ? (
              qualityReportsQuery.isLoading ? (
                <Skeleton active paragraph={{ rows: 4 }} />
              ) : (
                <Table<DataQualityReport>
                  rowKey={(record) => String(record.id)}
                  columns={reportColumns}
                  dataSource={reports}
                  loading={qualityReportsQuery.isFetching || qualityCheckMutation.isPending}
                  pagination={{
                    current: qualityParams.page,
                    pageSize: qualityParams.pageSize,
                    total: qualityReportsQuery.data?.total ?? 0,
                    showSizeChanger: false,
                    showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${formatNumber(total)} 条`,
                    onChange: (page, pageSize) => {
                      void navigate({
                        search: {
                          ...search,
                          qualityDatasetName: qualityParams.datasetName || undefined,
                          qualityCheckedAt: qualityParams.checkedAt || undefined,
                          qualityStatus: qualityParams.status || undefined,
                          qualitySeverity: qualityParams.severity || undefined,
                          qualityPage: page,
                          qualityPageSize: pageSize,
                        },
                      });
                    },
                  }}
                  scroll={{ x: 1440 }}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无质量报告" /> }}
                />
              )
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="默认不加载质量明细。先点击“查询”或“运行检查”再展开报告。"
              />
            )}
          </Space>
        )}
      </Card>
    </div>
  );
}
