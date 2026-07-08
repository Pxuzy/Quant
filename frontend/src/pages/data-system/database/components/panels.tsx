/**
 * Panel sub-components extracted from DatabaseManagementPage.
 */
import { Link } from '@tanstack/react-router';
import { CloudSyncOutlined, ProfileOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Empty, Skeleton, Space, Tag, Typography } from 'antd';
import type { DatabaseCoverageSummary, DatabaseIntegrationOverview, DatasetSnapshot } from '../../../../features/database/types';
import { formatDate, formatNumber, formatPercent } from '../../../../shared/components/formatters';
import { formatMarket, formatStorageType } from '../../../../shared/domain/labels';
import { StatusTag } from '../../../../shared/components/StatusTag';
import type { FreshnessItem } from './utils';
import {
  findRepairableDailyWatermark,
  getClosedLoopStatus,
  getDailyCompletenessPercent,
  getDatasetFreshnessItems,
  getFreshnessTagColor,
  getMarketRepairSearch,
  isCoverageDegraded,
  formatRange,
} from './utils';

export function DataClosedLoopPanel({
  overview,
  loading,
  error,
}: {
  overview?: DatabaseIntegrationOverview;
  loading: boolean;
  error: boolean;
}) {
  if (error) {
    return <Alert type="error" showIcon message="数据闭环状态加载失败" description="后端数据整合总览接口暂不可用。" />;
  }

  if (loading) {
    return (
      <Card className="database-panel database-closed-loop-card">
        <Skeleton active paragraph={{ rows: 3 }} />
      </Card>
    );
  }

  const coverage = overview?.coverage_summary;
  const summary = overview?.summary;
  const watermarks = overview?.sync_watermarks ?? [];
  const repairableDailyWatermark = findRepairableDailyWatermark(watermarks);
  const closedLoop = getClosedLoopStatus(coverage);
  const completeness = getDailyCompletenessPercent(coverage);
  const repairSearch = getMarketRepairSearch(coverage, repairableDailyWatermark);
  const coverageDegraded = isCoverageDegraded(coverage);
  const hasDailyGap = Boolean(coverage && !coverageDegraded && coverage.daily_missing_symbol_days > 0);

  return (
    <Card id="database-closed-loop-section" className="database-panel database-closed-loop-card">
      <div className="database-closed-loop">
        <div className="database-closed-loop-main">
          <Space direction="vertical" size={10}>
            <Space wrap size={[8, 8]}>
              <Tag color={closedLoop.color}>{closedLoop.label}</Tag>
              <Tag>{formatMarket(coverage?.market, '中国 A 股')}</Tag>
            </Space>
            <div>
              <Typography.Title level={4}>{closedLoop.title}</Typography.Title>
              <Typography.Text type="secondary">{closedLoop.description}</Typography.Text>
            </div>
            <Space wrap size={[10, 8]}>
              {hasDailyGap ? (
                <Link to="/data-system/sync-tasks" search={repairSearch}>
                  <Button type="primary" icon={<CloudSyncOutlined />}>
                    创建市场级补齐任务
                  </Button>
                </Link>
              ) : null}
              <Link to="/data-system/sync-tasks">
                <Button icon={<ProfileOutlined />}>查看同步调度</Button>
              </Link>
            </Space>
          </Space>
        </div>
        <div className="database-closed-loop-metrics">
          <div>
            <Typography.Text type="secondary">股票池</Typography.Text>
            <Typography.Title level={4}>{formatNumber(coverage?.stock_pool_total ?? 0)} 只</Typography.Title>
            <Typography.Text type="secondary">有日线 {formatNumber(coverage?.daily_covered_stock_count ?? 0)} 只</Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">日线完整度</Typography.Text>
            <Typography.Title level={4}>{formatPercent(completeness)}</Typography.Title>
            <Typography.Text type="secondary">
              {coverageDegraded
                ? '等待 Parquet / DuckDB 查询恢复'
                : `${formatNumber(coverage?.daily_actual_symbol_days ?? 0)} / ${formatNumber(coverage?.daily_expected_symbol_days ?? 0)}`}
            </Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">{coverageDegraded ? '覆盖率状态' : '待补股票-交易日'}</Typography.Text>
            <Typography.Title level={4}>{formatNumber(coverage?.daily_missing_symbol_days ?? 0)}</Typography.Title>
            <Typography.Text type="secondary">
              {coverageDegraded ? '暂不可确认' : formatRange(coverage?.coverage_start_date, coverage?.coverage_end_date)}
            </Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary">最近入库批次</Typography.Text>
            <Typography.Title level={4}>{formatNumber(summary?.recent_batches_total ?? 0)} 个</Typography.Title>
            <Typography.Text type="secondary">失败 {formatNumber(summary?.failed_batches_total ?? 0)} 个</Typography.Text>
          </div>
        </div>
      </div>
    </Card>
  );
}

export function CoverageSummaryPanel({
  coverage,
  loading,
  error,
}: {
  coverage?: DatabaseCoverageSummary;
  loading: boolean;
  error: boolean;
}) {
  if (error) {
    return <Alert type="error" showIcon message="覆盖率摘要加载失败" description="后端数据整合总览接口暂不可用。" />;
  }

  if (loading) {
    return <Skeleton active paragraph={{ rows: 3 }} />;
  }

  if (!coverage) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无覆盖率摘要" />;
  }

  const completeness =
    coverage.daily_completeness === undefined || coverage.daily_completeness === null
      ? undefined
      : coverage.daily_completeness * 100;
  const coverageDegraded = isCoverageDegraded(coverage);
  const hasDailyGap = !coverageDegraded && coverage.daily_missing_symbol_days > 0;
  return (
    <Space className="database-coverage-stack" direction="vertical" size={12}>
      {coverageDegraded ? (
        <Alert
          type="warning"
          showIcon
          message="覆盖率暂不可确认"
          description={coverage.coverage_message ?? 'Parquet / DuckDB 覆盖率查询失败，当前覆盖率按未知处理。'}
        />
      ) : null}
      <div className="database-coverage-grid">
        <div className="database-coverage-item">
          <Typography.Text type="secondary">股票池覆盖</Typography.Text>
          <Typography.Title level={4}>{formatNumber(coverage.stock_pool_total)} 只</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag color="blue">{formatMarket(coverage.market)}</Tag>
            <Tag>有日线 {formatNumber(coverage.daily_covered_stock_count)} 只</Tag>
          </Space>
        </div>
        <div className="database-coverage-item">
          <Typography.Text type="secondary">交易日历覆盖</Typography.Text>
          <Typography.Title level={4}>{formatRange(coverage.coverage_start_date, coverage.coverage_end_date)}</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag color="cyan">最新 {formatDate(coverage.calendar_latest_date)}</Tag>
            <Tag>{formatMarket(coverage.market)}</Tag>
          </Space>
        </div>
        <div className="database-coverage-item">
          <Typography.Text type="secondary">日线完整度</Typography.Text>
          <Typography.Title level={4}>{formatPercent(completeness)}</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag>应有 {formatNumber(coverage.daily_expected_symbol_days)}</Tag>
            <Tag color={coverageDegraded ? 'warning' : 'green'}>
              {coverageDegraded ? '已有暂不可确认' : `已有 ${formatNumber(coverage.daily_actual_symbol_days)}`}
            </Tag>
          </Space>
        </div>
        <div className="database-coverage-item">
          <Typography.Text type="secondary">{coverageDegraded ? '覆盖率状态' : '缺失股票-交易日'}</Typography.Text>
          <Typography.Title level={4}>{formatNumber(coverage.daily_missing_symbol_days)}</Typography.Title>
          <Space wrap size={[6, 6]}>
            <Tag color={coverageDegraded ? 'warning' : hasDailyGap ? 'warning' : 'green'}>
              {coverageDegraded ? '暂不可确认' : '待补数据'}
            </Tag>
            <Tag>按股票 x 开市日统计</Tag>
          </Space>
        </div>
      </div>
      {hasDailyGap ? (
        <Alert
          type="warning"
          showIcon
          message="检测到市场级日线缺口"
          description={`建议从同步调度创建市场级日线缺口补齐任务，范围 ${formatRange(coverage.coverage_start_date, coverage.coverage_end_date)}（最近半年）。`}
          action={
            <Link to="/data-system/sync-tasks" search={getMarketRepairSearch(coverage)}>
              <Button size="small" type="primary">
                去补齐日线
              </Button>
            </Link>
          }
        />
      ) : null}
    </Space>
  );
}

export function DataFreshnessPanel({
  snapshots,
  loading,
  error,
}: {
  snapshots: DatasetSnapshot[];
  loading: boolean;
  error: boolean;
}) {
  if (error) {
    return <Alert type="error" showIcon message="数据新鲜度加载失败" description="后端数据整合总览接口暂不可用。" />;
  }

  if (loading) {
    return <Skeleton active paragraph={{ rows: 3 }} />;
  }

  const items = getDatasetFreshnessItems(snapshots);
  return (
    <div className="database-freshness-grid">
      {items.map((item) => (
        <div className="database-freshness-item" key={item.datasetName}>
          <div className="database-freshness-head">
            <Space direction="vertical" size={0}>
              <Typography.Text strong>{item.title}</Typography.Text>
              <Typography.Text type="secondary">{item.description}</Typography.Text>
            </Space>
            <StatusTag value={item.qualityStatus} />
          </div>
          <div className="database-freshness-date">
            <Typography.Text type="secondary">最新日期</Typography.Text>
            <Typography.Title level={4}>{formatDate(item.latestDate)}</Typography.Title>
          </div>
          <Space wrap size={[6, 6]}>
            <Tag color={getFreshnessTagColor(item)}>{item.latestDate ? '已有数据' : '待同步'}</Tag>
            <Tag>{formatStorageType(item.storageType || '-')}</Tag>
            <Tag>{formatNumber(item.rowCount)} 行</Tag>
            <Tag color="blue">来源 {item.source || '-'}</Tag>
          </Space>
          <Link to={item.actionPath} search={item.actionSearch}>
            <Button type="link" size="small">
              {item.actionLabel}
            </Button>
          </Link>
        </div>
      ))}
    </div>
  );
}

