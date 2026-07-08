import { useMemo, useRef } from 'react';
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router';
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  ProfileOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Alert, App as AntApp, Button, Card, Col, Descriptions, Empty, Progress, Row, Skeleton, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useDailyBarsQuery, useSyncDailyBarsMutation } from '../../../features/market-data/api';
import type { DailyBar } from '../../../features/market-data/types';
import type { KLine } from '../../../features/market/api';
import {
  useStockDailyCoverageQuery,
  useStockDailyIngestBatchesQuery,
  useStockDailyQualityQuery,
  useStockQuery,
} from '../../../features/stocks/api';
import type { StockDailyCoverage, StockDailyIngestBatch, StockDailyQuality } from '../../../features/stocks/types';
import { StatusTag } from '../../../shared/components/StatusTag';
import { StockKlineChart } from '../../../shared/components/StockKlineChart';
import {
  formatDate,
  formatDateTime,
  formatDecimal,
  formatNumber,
  formatPercent,
  formatSignedDecimal,
} from '../../../shared/components/formatters';
import { formatAdjustType, formatExchange, formatMarket } from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';
// Extracted helpers
import {CHART_HEIGHT,
  CHART_PADDING,
  CHART_WIDTH,
  DETAIL_DAILY_PAGE_SIZE,
  DETAIL_KLINE_HISTORY_LIMIT,
  TABLE_PREVIEW_SIZE,
  buildChartModel,
  buildDataProfile,
  buildDailyBackfillRange,
  buildIndicatorSummary,
  buildQualitySummary,
  dailyBarToKLine,
  formatCoveragePercent,
  getBatchErrorMessage,
  getBatchLineageSearch,
  getBatchQualityStatus,
  getBatchRecordsWritten,
  getBatchRequestedSource,
  getBatchSchemaVersion,
  getBatchNormalizeVersion,
  getBatchStartedAt,
  getBatchFinishedAt,
  getBatchTaskId,
  getLatestIngestBatch,
  getNumericBatchId,
  getNumericTaskId,
  getStockQualityDecision,
  normalizeStockRouteSymbol,
  normalizeV1Market,
  sortDailyRows,
  formatBatchRange,
} from './components/utils';
import { buildDailyColumns } from './components/columns';
import { CloseVolumeChart, QualityTags } from './components/charts';

export function StockDetailPage() {
  const { message } = AntApp.useApp();
  const pageRef = useRef<HTMLDivElement>(null);
  const params = useParams({ from: '/data-system/stocks/$symbol' });
  const search = useSearch({ from: '/data-system/stocks/$symbol' });
  const navigate = useNavigate({ from: '/data-system/stocks/$symbol' });
  const rawSymbol = params.symbol;
  const symbol = normalizeStockRouteSymbol(rawSymbol);
  const displayCode = rawSymbol.toUpperCase();
  const market = normalizeV1Market(search.market);
  const stockQuery = useStockQuery(symbol, market);
  const coverageQuery = useStockDailyCoverageQuery(symbol, market);
  const dailyQualityQuery = useStockDailyQualityQuery(symbol, market);
  const ingestBatchesQuery = useStockDailyIngestBatchesQuery(symbol, market);
  const syncDailyBarsMutation = useSyncDailyBarsMutation();
  const dailyBarsQuery = useDailyBarsQuery({
    symbol,
    market,
    sortOrder: 'desc',
    page: 1,
    pageSize: DETAIL_DAILY_PAGE_SIZE,
  });
  const rows = dailyBarsQuery.data?.items ?? [];
  const sortedRows = useMemo(() => sortDailyRows(rows), [rows]);
  const klineRows = useMemo(() => sortedRows.map(dailyBarToKLine), [sortedRows]);
  const latestRows = useMemo(() => [...sortedRows].reverse().slice(0, TABLE_PREVIEW_SIZE), [sortedRows]);
  const indicators = useMemo(() => buildIndicatorSummary(sortedRows), [sortedRows]);
  const sampleQuality = useMemo(() => buildQualitySummary(sortedRows), [sortedRows]);
  const dataProfile = useMemo(() => buildDataProfile(sortedRows, dailyBarsQuery.data?.total), [dailyBarsQuery.data?.total, sortedRows]);
  const chartModel = useMemo(() => buildChartModel(sortedRows), [sortedRows]);
  const dailyColumns = useMemo(() => buildDailyColumns(), []);
  const stock = stockQuery.data;
  const coverage = coverageQuery.data;
  const dailyQuality = dailyQualityQuery.data;
  const displayTitle = stock?.name ? `${stock.name} ${displayCode}` : displayCode;
  const ingestBatches = ingestBatchesQuery.data?.items ?? [];
  const latestIngestBatch = useMemo(() => getLatestIngestBatch(ingestBatches), [ingestBatches]);
  const completeness =
    dailyQuality?.data_completeness ??
    coverage?.data_completeness ??
    stock?.data_completeness ??
    stock?.dataCompleteness;
  const completenessPercent = completeness === undefined || completeness === null ? undefined : Math.round(completeness * 100);
  const qualityMissingTradeDays = dailyQuality?.missing_trade_days ?? coverage?.missing_trade_days ?? 0;
  const dailyBackfillRange = useMemo(
    () => buildDailyBackfillRange(dailyQuality, coverage, dataProfile.rowCount),
    [coverage, dailyQuality, dataProfile.rowCount],
  );
  const qualityDecision = useMemo(
    () =>
      getStockQualityDecision({
        dailyQuality,
        coverage,
        latestBatch: latestIngestBatch,
        sampleQuality,
      }),
    [coverage, dailyQuality, latestIngestBatch, sampleQuality],
  );
  const quoteTrendClass = indicators.change === undefined ? 'is-flat' : indicators.change < 0 ? 'is-down' : 'is-up';

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }
      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.04, y: 8 });
      fadeInUp(root.querySelectorAll('.stock-detail-panel'), { delay: 0.08, stagger: 0.035, y: 10 });
    },
    { scope: pageRef },
  );

  const refetchDailyData = () => {
    void stockQuery.refetch();
    void coverageQuery.refetch();
    void dailyQualityQuery.refetch();
    void ingestBatchesQuery.refetch();
    void dailyBarsQuery.refetch();
  };

  const handleDailyBackfillSync = () => {
    syncDailyBarsMutation.mutate(
      {
        source: 'auto',
        market,
        symbol,
        start_date: dailyBackfillRange.startDate,
        end_date: dailyBackfillRange.endDate,
      },
      {
        onSuccess: (task) => {
          const suffix = task.id ? ` #${task.id}` : '';
          void message.success(`日线同步任务已创建${suffix}，已进入同步调度查看执行结果`);
          refetchDailyData();
          const taskId = Number(task.id);
          void navigate({
            to: '/data-system/sync-tasks',
            search: {
              focus: 'daily-bars',
              taskId: Number.isFinite(taskId) ? taskId : undefined,
              market,
              symbol,
              startDate: dailyBackfillRange.startDate,
              endDate: dailyBackfillRange.endDate,
              page: 1,
              pageSize: 10,
            },
          });
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '日线同步任务创建失败');
        },
      },
    );
  };

  return (
    <div className="workbench stock-detail-page" ref={pageRef}>
      <section className={`stock-terminal-quote motion-summary-card ${quoteTrendClass}`}>
        <div className="stock-terminal-identity">
          <Link to="/data-system/stocks" search={{ market }} className="stock-detail-back">
            <ArrowLeftOutlined /> 返回股票池
          </Link>
          <div className="stock-terminal-title-row">
            <Typography.Title level={3}>{displayTitle}</Typography.Title>
            {stock?.status ? <StatusTag value={stock.status} /> : null}
          </div>
          <Typography.Text type="secondary">
            {formatExchange(stock?.exchange)} / {stock?.industry || '未分类'} / 最新数据日 {formatDate(stock?.latest_data_date ?? stock?.latestDataDate)}
          </Typography.Text>
        </div>

        <div className="stock-terminal-price">
          <Typography.Text type="secondary">最新收盘</Typography.Text>
          <strong className="stock-terminal-price-value">{formatDecimal(indicators.latest?.close)}</strong>
          <span className="stock-terminal-change">
            {formatSignedDecimal(indicators.change)} / {formatPercent(indicators.changePct)}
          </span>
        </div>

        <div className="stock-terminal-stat-grid">
          <div><span>开</span><strong>{formatDecimal(indicators.latest?.open)}</strong></div>
          <div><span>高</span><strong>{formatDecimal(indicators.latest?.high)}</strong></div>
          <div><span>低</span><strong>{formatDecimal(indicators.latest?.low)}</strong></div>
          <div><span>收</span><strong>{formatDecimal(indicators.latest?.close)}</strong></div>
          <div><span>量</span><strong>{formatNumber(indicators.latest?.volume)}</strong></div>
          <div><span>额</span><strong>{formatNumber(indicators.latest?.amount)}</strong></div>
          <div><span>MA5</span><strong>{formatDecimal(indicators.ma5)}</strong></div>
          <div><span>MA20</span><strong>{formatDecimal(indicators.ma20)}</strong></div>
          <div><span>完整度</span><strong>{formatCoveragePercent(completeness)}</strong></div>
        </div>

        <Space className="stock-terminal-actions" size={8}>
          <Button
            icon={<ReloadOutlined />}
            loading={stockQuery.isFetching || coverageQuery.isFetching || dailyBarsQuery.isFetching}
            onClick={() => {
              void stockQuery.refetch();
              void coverageQuery.refetch();
              void dailyQualityQuery.refetch();
              void ingestBatchesQuery.refetch();
              void dailyBarsQuery.refetch();
            }}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<SyncOutlined spin={syncDailyBarsMutation.isPending} />}
            loading={syncDailyBarsMutation.isPending}
            disabled={!symbol || stockQuery.isError}
            onClick={handleDailyBackfillSync}
          >
            {dailyBackfillRange.buttonText}
          </Button>
        </Space>
      </section>

      {stockQuery.isError ? (
        <Alert className="stock-detail-panel" type="error" showIcon message="股票详情加载失败" description="该股票可能不存在，或后端股票接口暂不可用。" />
      ) : null}

      <Row gutter={[16, 16]} align="stretch" className="stock-terminal-body">
        <Col span={8} className="stock-terminal-side-rail">
          <Card
            className="stock-detail-panel stock-lineage-card"
            title="数据追溯摘要"
            extra={
              latestIngestBatch ? (
                <Space wrap size={4}>
                  <Link
                    to="/data-system/database"
                    search={getBatchLineageSearch(latestIngestBatch, { market, symbol })}
                  >
                    <Button type="link" icon={<DatabaseOutlined />}>
                      血缘
                    </Button>
                  </Link>
                  {getNumericTaskId(latestIngestBatch) ? (
                    <Link
                      to="/data-system/sync-tasks"
                      search={{ taskId: getNumericTaskId(latestIngestBatch), page: 1, pageSize: 10 }}
                    >
                      <Button type="link" icon={<ProfileOutlined />}>
                        同步记录
                      </Button>
                    </Link>
                  ) : null}
                </Space>
              ) : null
            }
          >
            {dailyBarsQuery.isLoading || ingestBatchesQuery.isLoading ? (
              <Skeleton active paragraph={{ rows: 2 }} />
            ) : ingestBatchesQuery.isError ? (
              <Alert type="error" showIcon message="追溯信息加载失败" description="后端日线入库批次接口暂不可用。" />
            ) : latestIngestBatch ? (
              <div className="stock-lineage-grid">
                <div>
                  <Typography.Text type="secondary">最新批次</Typography.Text>
                  <Space wrap size={6}>
                    <Typography.Text strong>#{latestIngestBatch.id}</Typography.Text>
                    <StatusTag value={latestIngestBatch.status} />
                    <StatusTag value={getBatchQualityStatus(latestIngestBatch)} />
                  </Space>
                </div>
                <div>
                  <Typography.Text type="secondary">实际来源</Typography.Text>
                  <Typography.Text strong>{latestIngestBatch.source || '-'}</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">同步范围</Typography.Text>
                  <Typography.Text strong>{formatBatchRange(latestIngestBatch)}</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">写入记录</Typography.Text>
                  <Typography.Text strong>{formatNumber(getBatchRecordsWritten(latestIngestBatch))} 行</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">请求来源</Typography.Text>
                  <Typography.Text strong>{getBatchRequestedSource(latestIngestBatch) || '-'}</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">数据契约</Typography.Text>
                  <Typography.Text strong>
                    Schema {getBatchSchemaVersion(latestIngestBatch)} / Normalize {getBatchNormalizeVersion(latestIngestBatch)}
                  </Typography.Text>
                </div>
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日线入库批次。同步该股票日线后，这里会显示来源、批次、Schema 和质量结果。" />
            )}
          </Card>

          <Card className="stock-detail-panel" title="基础信息">
            {stockQuery.isLoading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : stock ? (
              <Descriptions bordered column={1} size="small">
                <Descriptions.Item label="代码">{stock.symbol}</Descriptions.Item>
                <Descriptions.Item label="名称">{stock.name}</Descriptions.Item>
                <Descriptions.Item label="交易所">{formatExchange(stock.exchange)}</Descriptions.Item>
                <Descriptions.Item label="市场">{formatMarket(stock.market)}</Descriptions.Item>
                <Descriptions.Item label="行业">{stock.industry || '未分类'}</Descriptions.Item>
                <Descriptions.Item label="上市日期">{formatDate(stock.listing_date ?? stock.listingDate)}</Descriptions.Item>
                <Descriptions.Item label="最新数据日">{formatDate(stock.latest_data_date ?? stock.latestDataDate)}</Descriptions.Item>
                <Descriptions.Item label="数据完整度">{formatCoveragePercent(stock.data_completeness ?? stock.dataCompleteness)}</Descriptions.Item>
                <Descriptions.Item label="状态"><StatusTag value={stock.status} /></Descriptions.Item>
                <Descriptions.Item label="来源">{stock.source || '-'}</Descriptions.Item>
                <Descriptions.Item label="更新时间">{formatDateTime(stock.updated_at ?? stock.updatedAt)}</Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无股票基础信息" />
            )}
          </Card>

          <Card className="stock-detail-panel" title="新闻">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="新闻待补充，第一版先不接真实新闻源。" />
          </Card>

          <Card className="stock-detail-panel" title="数据口径">
            {dailyBarsQuery.isLoading || dailyQualityQuery.isLoading || ingestBatchesQuery.isLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : ingestBatchesQuery.isError ? (
              <Alert type="error" showIcon message="入库批次加载失败" description="后端批次追溯接口暂不可用。" />
            ) : (
              <Space className="stock-data-profile" direction="vertical" size={10}>
                <div>
                  <Typography.Text type="secondary">行情样本</Typography.Text>
                  <Typography.Text strong>{formatNumber(dataProfile.rowCount)} 条</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">日期范围</Typography.Text>
                  <Typography.Text strong>
                    {formatDate(dataProfile.firstDate)} ~ {formatDate(dataProfile.latestDate)}
                  </Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">复权口径</Typography.Text>
                  <Space wrap size={[6, 6]}>
                    {(dailyQuality?.adjust_types?.length ? dailyQuality.adjust_types : dataProfile.adjustTypeList).map((adjustType) => (
                      <Tag key={adjustType}>{formatAdjustType(adjustType)}</Tag>
                    ))}
                    {!dailyQuality?.adjust_types?.length && dataProfile.adjustTypeList.length === 0 ? <Tag>暂无</Tag> : null}
                  </Space>
                </div>
                <div>
                  <Typography.Text type="secondary">实际来源</Typography.Text>
                  <Space wrap size={[6, 6]}>
                    {(dailyQuality?.sources?.length ? dailyQuality.sources : dataProfile.sourceList).map((source) => (
                      <Tag color="blue" key={source}>{source}</Tag>
                    ))}
                    {!dailyQuality?.sources?.length && dataProfile.sourceList.length === 0 ? <Tag>暂无</Tag> : null}
                  </Space>
                </div>
                <div>
                  <Typography.Text type="secondary">最近入库</Typography.Text>
                  <Typography.Text>{formatDateTime(dataProfile.latestIngestedAt)}</Typography.Text>
                </div>
                <div className="stock-ingest-batches">
                  <Typography.Text type="secondary">最近批次</Typography.Text>
                  {ingestBatches.length === 0 ? (
                    <Typography.Text type="secondary">暂无日线入库批次</Typography.Text>
                  ) : (
                    <Space direction="vertical" size={8}>
                      {ingestBatches.slice(0, 3).map((batch) => (
                        <div className="stock-ingest-batch-item" key={batch.id}>
                          <Space className="stock-ingest-batch-heading" wrap>
                            <Typography.Text strong>批次 #{batch.id}</Typography.Text>
                            <StatusTag value={batch.status} />
                            <StatusTag value={getBatchQualityStatus(batch)} />
                            {getNumericBatchId(batch) ? (
                              <Link
                                to="/data-system/database"
                                search={getBatchLineageSearch(batch, { market, symbol })}
                              >
                                <Button type="link" size="small" icon={<DatabaseOutlined />}>
                                  血缘
                                </Button>
                              </Link>
                            ) : null}
                            {getNumericTaskId(batch) ? (
                              <Link
                                to="/data-system/sync-tasks"
                                search={{ taskId: getNumericTaskId(batch), page: 1, pageSize: 10 }}
                              >
                                <Button type="link" size="small" icon={<ProfileOutlined />}>
                                  查看同步记录
                                </Button>
                              </Link>
                            ) : null}
                          </Space>
                          <Typography.Text type="secondary">
                            任务 #{getBatchTaskId(batch) ?? '-'} / {formatBatchRange(batch)}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            来源 {batch.source || '-'}，请求 {getBatchRequestedSource(batch) || '-'}，写入 {formatNumber(getBatchRecordsWritten(batch))} 行
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            schema {getBatchSchemaVersion(batch)} / normalize {getBatchNormalizeVersion(batch)}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {formatDateTime(getBatchStartedAt(batch))} ~ {formatDateTime(getBatchFinishedAt(batch))}
                          </Typography.Text>
                          {getBatchErrorMessage(batch) ? (
                            <Typography.Text type="danger">{getBatchErrorMessage(batch)}</Typography.Text>
                          ) : null}
                        </div>
                      ))}
                    </Space>
                  )}
                </div>
                <Typography.Text type="secondary">股票详情只读取系统标准 API，不直接调用 AKShare、BaoStock 或 Tushare。</Typography.Text>
              </Space>
            )}
          </Card>
        </Col>

        <Col span={16} className="stock-terminal-main">
          <Card className="stock-detail-panel stock-detail-chart-card" title="K 线研究">
            <StockKlineChart
              code={rawSymbol}
              title={displayTitle}
              embedded
              minHeight={520}
              historyLimit={DETAIL_KLINE_HISTORY_LIMIT}
              data={klineRows}
              dataLoading={dailyBarsQuery.isLoading}
            />
          </Card>

          <Row gutter={[16, 16]} align="stretch">
            <Col span={12}>
              <Card className="stock-detail-panel" title="指标">
                <Space className="stock-detail-indicators" direction="vertical" size={10}>
                  <div><span>MA5</span><strong>{formatDecimal(indicators.ma5)}</strong></div>
                  <div><span>MA10</span><strong>{formatDecimal(indicators.ma10)}</strong></div>
                  <div><span>MA20</span><strong>{formatDecimal(indicators.ma20)}</strong></div>
                  <div><span>成交量 5 日均值</span><strong>{formatNumber(Math.round(indicators.volumeAvg5 ?? 0))}</strong></div>
                  <div><span>成交量 20 日均值</span><strong>{formatNumber(Math.round(indicators.volumeAvg20 ?? 0))}</strong></div>
                </Space>
              </Card>
            </Col>
            <Col span={12}>
              <Card
                className="stock-detail-panel"
                title="数据质量"
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined spin={syncDailyBarsMutation.isPending} />}
                    loading={syncDailyBarsMutation.isPending}
                    disabled={!symbol || stockQuery.isError}
                    onClick={handleDailyBackfillSync}
                  >
                    {dailyBackfillRange.buttonText}
                  </Button>
                }
              >
                {dailyQualityQuery.isError ? (
                  <Alert type="error" showIcon message="质量摘要加载失败" description="后端股票质量接口暂不可用。" />
                ) : dailyQualityQuery.isLoading ? (
                  <Skeleton active paragraph={{ rows: 4 }} />
                ) : dailyQuality && dailyQuality.checked_rows <= 0 ? (
                  <Space className="stock-quality-stack" direction="vertical" size={12}>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无质量摘要" />
                    <div className="stock-quality-backfill">
                      <Typography.Text type="secondary">同步范围</Typography.Text>
                      <Typography.Text strong>
                        {formatDate(dailyBackfillRange.startDate)} ~ {formatDate(dailyBackfillRange.endDate)}
                      </Typography.Text>
                    </div>
                  </Space>
                ) : (
                  <Space className="stock-quality-stack" direction="vertical" size={12}>
                    <div className="stock-quality-coverage">
                      <div>
                        <Space size={6}>
                          <Typography.Text type="secondary">后端质量摘要</Typography.Text>
                          <StatusTag value={dailyQuality?.status} />
                        </Space>
                        <Typography.Title level={4}>{formatCoveragePercent(completeness)}</Typography.Title>
                      </div>
                      <Progress
                        type="circle"
                        size={68}
                        percent={completenessPercent}
                        status={dailyQuality?.status === 'error' ? 'exception' : qualityMissingTradeDays ? 'normal' : 'success'}
                      />
                    </div>
                    <div className="stock-quality-decision">
                      <div>
                        <Space size={[6, 6]} wrap>
                          <StatusTag value={qualityDecision.status} />
                          <Typography.Text strong>{qualityDecision.title}</Typography.Text>
                        </Space>
                        <Typography.Text type="secondary">{qualityDecision.description}</Typography.Text>
                      </div>
                      <Space wrap>
                        {latestIngestBatch && latestIngestBatch.status === 'failed' && getNumericTaskId(latestIngestBatch) ? (
                          <Link
                            to="/data-system/sync-tasks"
                            search={{ taskId: getNumericTaskId(latestIngestBatch), page: 1, pageSize: 10 }}
                          >
                            <Button size="small" icon={<ProfileOutlined />}>
                              {qualityDecision.actionLabel}
                            </Button>
                          </Link>
                        ) : (
                          <Button
                            size="small"
                            type={qualityDecision.status === 'good' ? 'default' : 'primary'}
                            icon={<SyncOutlined spin={syncDailyBarsMutation.isPending} />}
                            loading={syncDailyBarsMutation.isPending}
                            disabled={!symbol || stockQuery.isError}
                            onClick={handleDailyBackfillSync}
                          >
                            {qualityDecision.actionLabel}
                          </Button>
                        )}
                        {latestIngestBatch ? (
                          <Link to="/data-system/database" search={getBatchLineageSearch(latestIngestBatch, { market, symbol })}>
                            <Button size="small" icon={<DatabaseOutlined />}>
                              看血缘
                            </Button>
                          </Link>
                        ) : null}
                      </Space>
                    </div>
                    <Space wrap size={[8, 8]}>
                      <Tag color="blue">覆盖窗口 {formatDate(dailyQuality?.first_data_date)} ~ {formatDate(dailyQuality?.latest_data_date)}</Tag>
                      <Tag>应有 {formatNumber(dailyQuality?.expected_trade_days ?? 0)} 日</Tag>
                      <Tag color="green">已有 {formatNumber(dailyQuality?.actual_trade_days ?? 0)} 日</Tag>
                      <Tag color={qualityMissingTradeDays ? 'warning' : 'green'}>
                        缺失 {formatNumber(qualityMissingTradeDays)} 日
                      </Tag>
                      <Tag color={dailyQuality?.duplicate_daily_keys ? 'red' : 'green'}>
                        重复主键 {formatNumber(dailyQuality?.duplicate_daily_keys ?? 0)}
                      </Tag>
                      <Tag color={dailyQuality?.ohlc_error_count ? 'red' : 'green'}>
                        OHLC 异常 {formatNumber(dailyQuality?.ohlc_error_count ?? 0)}
                      </Tag>
                      <Tag color={dailyQuality?.negative_price_count ? 'red' : 'green'}>
                        负价格 {formatNumber(dailyQuality?.negative_price_count ?? 0)}
                      </Tag>
                      <Tag color={dailyQuality?.negative_volume_count || dailyQuality?.negative_amount_count ? 'red' : 'green'}>
                        负成交 {formatNumber((dailyQuality?.negative_volume_count ?? 0) + (dailyQuality?.negative_amount_count ?? 0))}
                      </Tag>
                    </Space>
                    {dailyQuality?.missing_trade_date_samples?.length ? (
                      <Typography.Text type="secondary">
                        缺失样例：{dailyQuality.missing_trade_date_samples.map((date) => formatDate(date)).join('、')}
                      </Typography.Text>
                    ) : (
                      <Typography.Text type="secondary">当前覆盖窗口内未发现缺失交易日。</Typography.Text>
                    )}
                    <Typography.Text type="secondary">
                      复权口径：{dailyQuality?.adjust_types?.length ? dailyQuality.adjust_types.map((item) => formatAdjustType(item)).join('、') : '-'}；来源：
                      {dailyQuality?.sources?.length ? dailyQuality.sources.join('、') : '-'}；检查行数 {formatNumber(dailyQuality?.checked_rows ?? 0)}
                    </Typography.Text>
                    <div className="stock-quality-backfill">
                      <Typography.Text type="secondary">{dailyBackfillRange.label}</Typography.Text>
                      <Typography.Text strong>
                        {formatDate(dailyBackfillRange.startDate)} ~ {formatDate(dailyBackfillRange.endDate)}
                      </Typography.Text>
                    </div>
                    <div className="stock-quality-sample">
                      <Typography.Text type="secondary">当前表格样本预检（最近 120 条）</Typography.Text>
                      <QualityTags summary={sampleQuality} />
                    </div>
                  </Space>
                )}
              </Card>
            </Col>
          </Row>

          <Card
            className="stock-detail-panel stock-detail-table-card"
            title={`最近日线预览（${formatNumber(latestRows.length)} / ${formatNumber(dataProfile.rowCount)} 条）`}
          >
            <Table<DailyBar>
              rowKey={(record) => `${record.symbol}-${record.exchange}-${record.trade_date}-${record.adjust_type}`}
              columns={dailyColumns}
              dataSource={latestRows}
              loading={dailyBarsQuery.isFetching}
              pagination={false}
              scroll={{ x: 980 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日线数据" /> }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}