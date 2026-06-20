import { useMemo, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  BarChartOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Col, Empty, Progress, Row, Skeleton, Space, Statistic, Tag, Typography } from 'antd';
import { useDataQualityOverviewQuery } from '../../../features/data-quality/api';
import { useDatabaseIntegrationOverviewQuery, useDatabaseStatusQuery } from '../../../features/database/api';
import type { DatabaseCoverageSummary, RecentIngestBatch } from '../../../features/database/types';
import { formatBytes, formatDate, formatNumber } from '../../../shared/components/formatters';
import { formatCapability } from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

function coveragePercent(coverage?: DatabaseCoverageSummary) {
  if (!coverage?.daily_completeness && coverage?.daily_completeness !== 0) {
    return 0;
  }
  return Math.round(coverage.daily_completeness * 100);
}

function qualityPassRate(total?: number, passed?: number) {
  if (!total) {
    return 0;
  }
  return Math.round(((passed ?? 0) / total) * 100);
}

function daysSince(value?: string | null) {
  if (!value) {
    return undefined;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  return Math.max(0, Math.floor((Date.now() - parsed) / 86_400_000));
}

function formatDataAge(days?: number) {
  if (days === undefined) {
    return '未知';
  }
  if (days === 0) {
    return '今天';
  }
  return `${formatNumber(days)} 天前`;
}

function hasDailyCoverageGap(coverage?: DatabaseCoverageSummary) {
  if (!coverage?.stock_pool_total) {
    return false;
  }
  return (coverage.daily_covered_stock_count ?? 0) < coverage.stock_pool_total;
}

function getBatchFinishedAt(batch: RecentIngestBatch) {
  return batch.finished_at ?? batch.started_at;
}

function getBatchRange(batch: RecentIngestBatch) {
  if (!batch.start_date && !batch.end_date) {
    return '-';
  }
  if (batch.start_date && batch.end_date && batch.start_date !== batch.end_date) {
    return `${formatDate(batch.start_date)} ~ ${formatDate(batch.end_date)}`;
  }
  return formatDate(batch.end_date || batch.start_date);
}

export function NumericSummaryPage() {
  const pageRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const databaseStatusQuery = useDatabaseStatusQuery();
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: 'A_SHARE' });
  const qualityOverviewQuery = useDataQualityOverviewQuery();

  const integrationOverview = integrationOverviewQuery.data;
  const coverage = integrationOverview?.coverage_summary;
  const summary = integrationOverview?.summary;
  const snapshots = integrationOverview?.dataset_snapshots ?? [];
  const recentBatches = integrationOverview?.recent_batches ?? [];

  // 数值汇总页只回答三个问题：数据新鲜到哪天、覆盖缺口在哪里、最近批次是否稳定。
  const latestBatch = useMemo(
    () =>
      [...recentBatches].sort((left, right) => {
        const leftTime = Date.parse(getBatchFinishedAt(left));
        const rightTime = Date.parse(getBatchFinishedAt(right));
        return rightTime - leftTime;
      })[0],
    [recentBatches],
  );
  const recentBatchRows = useMemo(
    () =>
      [...recentBatches]
        .sort((left, right) => Date.parse(getBatchFinishedAt(right)) - Date.parse(getBatchFinishedAt(left)))
        .slice(0, 5),
    [recentBatches],
  );
  const latestWatermark = useMemo(
    () =>
      [...(integrationOverview?.sync_watermarks ?? [])].sort((left, right) => {
        const leftTime = Date.parse(left.last_success_at ?? left.latest_success_date ?? '');
        const rightTime = Date.parse(right.last_success_at ?? right.latest_success_date ?? '');
        return rightTime - leftTime;
      })[0],
    [integrationOverview?.sync_watermarks],
  );

  const datasetTotal = summary?.datasets_total ?? snapshots.length;
  const totalRows = summary?.total_rows ?? snapshots.reduce((sum, snapshot) => sum + (snapshot.row_count ?? 0), 0);
  const latestDataDate = summary?.latest_data_date;
  const latestDataAge = daysSince(latestDataDate);
  const coverageRate = coveragePercent(coverage);
  const stockPoolCount = coverage?.stock_pool_total ?? 0;
  const dailyCoveredCount = coverage?.daily_covered_stock_count ?? 0;
  const dailyMissingCount = Math.max(stockPoolCount - dailyCoveredCount, 0);
  const hasCoverageGap = hasDailyCoverageGap(coverage);
  const warningCount = qualityOverviewQuery.data?.reports_warning ?? 0;
  const errorCount = qualityOverviewQuery.data?.reports_error ?? 0;
  const qualityRate = qualityPassRate(qualityOverviewQuery.data?.datasets_total, qualityOverviewQuery.data?.datasets_good);
  const hasRisk = warningCount > 0 || errorCount > 0 || Boolean(coverage?.coverage_status && coverage.coverage_status !== 'ok');
  const isLoading = databaseStatusQuery.isLoading || integrationOverviewQuery.isLoading || qualityOverviewQuery.isLoading;
  const isError = databaseStatusQuery.isError || integrationOverviewQuery.isError || qualityOverviewQuery.isError;
  const duckDbStatus = databaseStatusQuery.data?.duckdb_engine_status === 'available' ? '可用' : '未启用';

  const assetItems = [
    {
      label: '股票池',
      value: formatNumber(stockPoolCount),
      detail: '当前市场股票基础库',
    },
    {
      label: '日线覆盖',
      value: `${formatNumber(dailyCoveredCount)} / ${formatNumber(stockPoolCount)}`,
      detail: hasCoverageGap ? `还差 ${formatNumber(dailyMissingCount)} 只` : '覆盖已到位',
    },
    {
      label: '数据湖',
      value: formatBytes(databaseStatusQuery.data?.data_lake_size_bytes),
      detail: `${formatNumber(databaseStatusQuery.data?.parquet_file_count ?? 0)} 个 Parquet 文件`,
    },
  ];

  const openDailySync = () => {
    void navigate({
      to: '/data-system/sync-tasks',
      search: {
        focus: hasCoverageGap ? 'daily-bars-market-repair' : 'daily-bars',
        market: coverage?.market ?? 'A_SHARE',
        startDate: coverage?.coverage_start_date ?? undefined,
        endDate: coverage?.coverage_end_date ?? undefined,
        syncSource: latestWatermark?.requested_source || latestWatermark?.source || undefined,
      },
    });
  };
  const openLatestBatchLineage = (batch?: RecentIngestBatch) => {
    if (!batch) {
      void navigate({ to: '/data-system/database' });
      return;
    }
    const batchId = Number(batch.id);
    void navigate({
      to: '/data-system/database',
      search: {
        lineageBatchId: Number.isFinite(batchId) ? batchId : undefined,
        lineageDatasetName: batch.dataset_name,
      },
    });
  };

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.04, y: 8 });
      fadeInUp(root.querySelectorAll('.numeric-panel'), { delay: 0.08, stagger: 0.04, y: 10 });
    },
    { scope: pageRef },
  );

  return (
    <div className="workbench data-command-page numeric-summary-page" ref={pageRef}>
      <div className="workbench-heading command-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>数值数据汇总</Typography.Title>
          <Typography.Text type="secondary">先看是否新、是否全、是否有风险，再决定下一步。</Typography.Text>
        </Space>
        <Space className="command-actions" wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void integrationOverviewQuery.refetch()}>
            刷新
          </Button>
          <Button type="primary" icon={<RightOutlined />} onClick={openDailySync}>
            去补日线
          </Button>
        </Space>
      </div>

      {isError ? <Alert type="warning" showIcon message="部分汇总接口暂不可用" description="页面会优先展示已经返回的数据，缺失项可稍后刷新。" /> : null}

      <Row gutter={[14, 14]} className="summary-row command-summary-row">
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-blue">
            <Statistic title="数据集" value={isLoading ? '-' : datasetTotal} prefix={<DatabaseOutlined />} />
            <Typography.Text type="secondary">纳入数值汇总的核心表</Typography.Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-green">
            <Statistic title="总记录" value={isLoading ? '-' : formatNumber(totalRows)} prefix={<BarChartOutlined />} />
            <Typography.Text type="secondary">股票池、日线和日历合计</Typography.Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-amber">
            <Statistic title="最新数据日" value={isLoading ? '-' : formatDate(latestDataDate)} prefix={<ClockCircleOutlined />} />
            <Typography.Text type="secondary">{isLoading ? '加载中' : formatDataAge(latestDataAge)}</Typography.Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-cyan">
            <Statistic title="质量通过率" value={isLoading ? '-' : qualityRate} suffix={isLoading ? undefined : '%'} prefix={<SafetyCertificateOutlined />} />
            <Typography.Text type="secondary">
              {isLoading ? '加载中' : `警告 ${warningCount} / 错误 ${errorCount}`}
            </Typography.Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[14, 14]} align="stretch">
        <Col span={12}>
          <Card className="numeric-panel" title="当前结论">
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : (
              <Space className="numeric-stack" direction="vertical" size={14}>
                <div className="numeric-spotlight">
                  <Typography.Text type="secondary">一句话判断</Typography.Text>
                  <Typography.Title level={4}>
                    {hasCoverageGap ? '股票池已经有了，最需要补齐日线覆盖' : hasRisk ? '先看质量风险，再进入明细' : '当前数值数据可以继续使用'}
                  </Typography.Title>
                  <Typography.Text type="secondary">
                    {hasCoverageGap
                      ? `日线只覆盖 ${formatNumber(dailyCoveredCount)} / ${formatNumber(stockPoolCount)} 只股票。`
                      : coverage?.coverage_message || '覆盖、质量和最近批次没有明显阻塞。'}
                  </Typography.Text>
                </div>

                <div className="numeric-progress-card">
                  <Space className="numeric-progress-head">
                    <Typography.Text strong>日线覆盖完整度</Typography.Text>
                    <Tag color={hasCoverageGap ? 'warning' : 'green'}>{hasCoverageGap ? '需要补齐' : '可用'}</Tag>
                  </Space>
                  <Progress percent={coverageRate} strokeColor="#2f6f9f" />
                  <Typography.Text type="secondary">
                    缺口 {formatNumber(dailyMissingCount)} 只，市场 {coverage?.market ?? 'A_SHARE'}
                  </Typography.Text>
                </div>

                <Alert
                  type={hasCoverageGap || hasRisk ? 'warning' : 'success'}
                  showIcon
                  message={hasCoverageGap ? '优先做市场级日线补齐' : '当前没有明显阻塞'}
                  description={hasCoverageGap ? '先把日线覆盖从股票池补齐，其他明细和报表可以后续再展开。' : '可以继续查看股票池、数据库或同步任务。'}
                />
              </Space>
            )}
          </Card>
        </Col>

        <Col span={12}>
          <Card className="numeric-panel" title="关键数据资产">
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : (
              <div className="numeric-bottom-grid">
                {assetItems.map((item) => (
                  <div key={item.label}>
                    <Typography.Text type="secondary">{item.label}</Typography.Text>
                    <Typography.Title level={4}>{item.value}</Typography.Title>
                    <Typography.Text type="secondary">{item.detail}</Typography.Text>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[14, 14]} align="stretch">
        <Col span={14}>
          <Card
            className="numeric-panel"
            title="最近同步证据"
            extra={
              <Button size="small" onClick={() => openLatestBatchLineage(latestBatch)}>
                看血缘
              </Button>
            }
          >
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : (
              <Space className="numeric-stack" direction="vertical" size={12}>
                <div className="numeric-batch-strip">
                  <div>
                    <Typography.Text type="secondary">最近批次</Typography.Text>
                    <Typography.Title level={5}>{latestBatch ? `#${latestBatch.id}` : '-'}</Typography.Title>
                    <Typography.Text type="secondary">
                      {latestBatch
                        ? `${formatCapability(latestBatch.dataset_name)} / ${latestBatch.source || '-'}`
                        : '暂无入库批次'}
                    </Typography.Text>
                  </div>
                  <div>
                    <Typography.Text type="secondary">schema / normalize</Typography.Text>
                    <Typography.Title level={5}>
                      {latestBatch ? `${latestBatch.schema_version} / ${latestBatch.normalize_version}` : '-'}
                    </Typography.Title>
                    <Typography.Text type="secondary">正式写入前的契约版本</Typography.Text>
                  </div>
                  <div>
                    <Typography.Text type="secondary">写入结果</Typography.Text>
                    <Typography.Title level={5}>{latestBatch ? formatNumber(latestBatch.records_written) : '-'}</Typography.Title>
                    <Typography.Text type={latestBatch?.status === 'failed' ? 'danger' : 'secondary'}>
                      {latestBatch?.error_message || latestBatch?.quality_status || '-'}
                    </Typography.Text>
                  </div>
                </div>
                <div className="numeric-mini-grid">
                  <div>
                    <Typography.Text type="secondary">请求 / 实际来源</Typography.Text>
                    <Typography.Text strong>
                      {latestBatch ? `${latestBatch.requested_source || '-'} -> ${latestBatch.source || '-'}` : '-'}
                    </Typography.Text>
                  </div>
                  <div>
                    <Typography.Text type="secondary">水位线来源</Typography.Text>
                    <Typography.Text strong>{latestWatermark?.requested_source || latestWatermark?.source || '-'}</Typography.Text>
                  </div>
                </div>
                <div className="numeric-batch-table">
                  <div className="numeric-batch-table-head">
                    <span>批次</span>
                    <span>数据集</span>
                    <span>范围</span>
                    <span>来源</span>
                    <span>写入</span>
                    <span>质量</span>
                  </div>
                  {recentBatchRows.length ? (
                    recentBatchRows.map((batch) => (
                      <button
                        className="numeric-batch-row"
                        key={`${batch.id}-${batch.dataset_name}`}
                        type="button"
                        onClick={() => openLatestBatchLineage(batch)}
                      >
                        <span>#{batch.id}</span>
                        <span>{formatCapability(batch.dataset_name)}</span>
                        <span>{getBatchRange(batch)}</span>
                        <span>{batch.source || '-'}</span>
                        <span>{formatNumber(batch.records_written)}</span>
                        <span>
                          <Tag color={batch.status === 'failed' ? 'red' : batch.quality_status === 'good' ? 'green' : 'warning'}>
                            {batch.quality_status || batch.status}
                          </Tag>
                        </span>
                      </button>
                    ))
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无最近批次" />
                  )}
                </div>
              </Space>
            )}
          </Card>
        </Col>

        <Col span={10}>
          <Card className="numeric-panel" title="下一步">
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : (
              <Space className="numeric-stack" direction="vertical" size={12}>
                <div className="numeric-risk-summary">
                  <Space className="numeric-risk-summary-head">
                    <Typography.Text type="secondary">处理优先级</Typography.Text>
                    <Tag color={hasCoverageGap || hasRisk ? 'warning' : 'green'}>
                      {hasCoverageGap || hasRisk ? '建议处理' : '状态正常'}
                    </Tag>
                  </Space>
                  <Typography.Title level={4}>
                    {hasCoverageGap ? '补齐市场级日线' : hasRisk ? '复核质量报告' : '继续查看股票明细'}
                  </Typography.Title>
                  <Typography.Text type="secondary">
                    {hasCoverageGap
                      ? `还差 ${formatNumber(dailyMissingCount)} 只股票，点“去补日线”进入同步任务。`
                      : hasRisk
                        ? `质量报告里有 ${formatNumber(warningCount + errorCount)} 条需要关注。`
                        : '核心数据已经可读，可以继续看股票池或数据库。'}
                  </Typography.Text>
                </div>
                <Space wrap>
                  <Button type="primary" icon={<RightOutlined />} onClick={openDailySync}>
                    去补日线
                  </Button>
                  <Button onClick={() => void navigate({ to: '/data-system/stocks' })}>看股票池</Button>
                  <Button onClick={() => void navigate({ to: '/data-system/database' })}>看数据库</Button>
                </Space>
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
