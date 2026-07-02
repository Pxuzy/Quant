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
import { StockKlineChart } from '../../../features/market/StockKlineChart';
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

const DETAIL_DAILY_PAGE_SIZE = 1000;
const TABLE_PREVIEW_SIZE = 20;
const V1_MARKET = 'A_SHARE';
const DETAIL_KLINE_HISTORY_LIMIT = 30000;
const CHART_WIDTH = 820;
const CHART_HEIGHT = 260;
const CHART_PADDING = { top: 18, right: 28, bottom: 34, left: 54 };
const DATE_DAY_MS = 86_400_000;
const MISSING_SAMPLE_PADDING_DAYS = 3;
const DEFAULT_INITIAL_SYNC_DAYS = 90;
const DEFAULT_REFRESH_SYNC_DAYS = 30;

type IndicatorSummary = {
  latest?: DailyBar;
  previous?: DailyBar;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  change?: number;
  changePct?: number;
  volumeAvg5?: number;
  volumeAvg20?: number;
};

type QualitySummary = {
  duplicateDates: number;
  priceErrors: number;
  missingSampleGaps: number;
  checkedRows: number;
};

type DataProfile = {
  rowCount: number;
  sourceList: string[];
  adjustTypeList: string[];
  firstDate?: string;
  latestDate?: string;
  latestIngestedAt?: string;
};

type DailyBackfillRange = {
  startDate: string;
  endDate: string;
  label: string;
  buttonText: string;
};

type StockQualityDecision = {
  status: string;
  title: string;
  description: string;
  actionLabel: string;
};

type ChartPoint = {
  x: number;
  y: number;
  row: DailyBar;
};

type CandleBar = {
  x: number;
  openY: number;
  closeY: number;
  highY: number;
  lowY: number;
  width: number;
  isUp: boolean;
  row: DailyBar;
};

type VolumeBar = {
  x: number;
  y: number;
  width: number;
  height: number;
  isUp: boolean;
};

type ChartModel = {
  rows: DailyBar[];
  points: ChartPoint[];
  candles: CandleBar[];
  volumeBars: VolumeBar[];
  linePath: string;
  areaPath: string;
  lowerBound: number;
  upperBound: number;
  minPrice: number;
  maxPrice: number;
  first: DailyBar;
  latest: DailyBar;
};

function sortDailyRows(rows: DailyBar[]) {
  return [...rows].sort((a, b) => a.trade_date.localeCompare(b.trade_date));
}

function normalizeV1Market(market?: string) {
  return market === V1_MARKET ? market : V1_MARKET;
}

function normalizeStockRouteSymbol(symbol: string) {
  return symbol.replace(/^(sh|sz|bj)/i, '');
}

function average(values: number[]) {
  if (!values.length) {
    return undefined;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function movingAverage(rows: DailyBar[], windowSize: number) {
  if (rows.length < windowSize) {
    return undefined;
  }
  return average(rows.slice(-windowSize).map((row) => row.close));
}

function buildIndicatorSummary(rows: DailyBar[]): IndicatorSummary {
  const sortedRows = sortDailyRows(rows);
  const latest = sortedRows[sortedRows.length - 1];
  const previous = sortedRows[sortedRows.length - 2];
  const change = latest && previous ? latest.close - previous.close : undefined;
  return {
    latest,
    previous,
    ma5: movingAverage(sortedRows, 5),
    ma10: movingAverage(sortedRows, 10),
    ma20: movingAverage(sortedRows, 20),
    change,
    changePct: change !== undefined && previous?.close ? (change / previous.close) * 100 : undefined,
    volumeAvg5: average(sortedRows.slice(-5).map((row) => row.volume)),
    volumeAvg20: average(sortedRows.slice(-20).map((row) => row.volume)),
  };
}

function buildQualitySummary(rows: DailyBar[]): QualitySummary {
  const dateCounts = new Map<string, number>();
  let priceErrors = 0;
  const sortedRows = sortDailyRows(rows);

  sortedRows.forEach((row) => {
    dateCounts.set(row.trade_date, (dateCounts.get(row.trade_date) ?? 0) + 1);
    if (
      row.open < 0 ||
      row.high < 0 ||
      row.low < 0 ||
      row.close < 0 ||
      row.high < row.low ||
      row.high < row.open ||
      row.high < row.close ||
      row.low > row.open ||
      row.low > row.close
    ) {
      priceErrors += 1;
    }
  });

  let missingSampleGaps = 0;
  for (let index = 1; index < sortedRows.length; index += 1) {
    const previous = new Date(sortedRows[index - 1].trade_date).getTime();
    const current = new Date(sortedRows[index].trade_date).getTime();
    const gapDays = Math.round((current - previous) / DATE_DAY_MS);
    if (gapDays > 10) {
      missingSampleGaps += 1;
    }
  }

  return {
    duplicateDates: [...dateCounts.values()].reduce((sum, count) => sum + Math.max(0, count - 1), 0),
    priceErrors,
    missingSampleGaps,
    checkedRows: rows.length,
  };
}

function getStockQualityDecision({
  dailyQuality,
  coverage,
  latestBatch,
  sampleQuality,
}: {
  dailyQuality?: StockDailyQuality;
  coverage?: StockDailyCoverage;
  latestBatch?: StockDailyIngestBatch;
  sampleQuality: QualitySummary;
}): StockQualityDecision {
  const latestBatchError = latestBatch && latestBatch.status === 'failed' ? getBatchErrorMessage(latestBatch) : undefined;
  const missingTradeDays = dailyQuality?.missing_trade_days ?? coverage?.missing_trade_days ?? 0;
  const duplicateKeys = dailyQuality?.duplicate_daily_keys ?? sampleQuality.duplicateDates;
  const ohlcErrors = dailyQuality?.ohlc_error_count ?? sampleQuality.priceErrors;
  const negativeValues =
    (dailyQuality?.negative_price_count ?? 0) +
    (dailyQuality?.negative_volume_count ?? 0) +
    (dailyQuality?.negative_amount_count ?? 0);

  if (latestBatchError) {
    return {
      status: 'error',
      title: '最近入库批次失败',
      description: latestBatchError,
      actionLabel: '查看同步记录',
    };
  }

  if (duplicateKeys > 0 || ohlcErrors > 0 || negativeValues > 0) {
    return {
      status: 'error',
      title: '字段质量需要处理',
      description: `发现重复主键 ${formatNumber(duplicateKeys)}、OHLC 异常 ${formatNumber(ohlcErrors)}、负值 ${formatNumber(negativeValues)}。`,
      actionLabel: '重新同步日线',
    };
  }

  if (missingTradeDays > 0) {
    return {
      status: 'warning',
      title: '日线覆盖有缺口',
      description: `缺失 ${formatNumber(missingTradeDays)} 个交易日，建议按下方范围补齐这只股票。`,
      actionLabel: '补齐日线',
    };
  }

  if (!dailyQuality || dailyQuality.checked_rows <= 0) {
    return {
      status: 'default',
      title: '还没有质量检查样本',
      description: '先同步这只股票的日线，系统会生成批次、来源和质量摘要。',
      actionLabel: '同步日线',
    };
  }

  return {
    status: 'good',
    title: '单股日线质量正常',
    description: '覆盖、主键、OHLC 和负值检查当前未发现需要处理的问题。',
    actionLabel: '刷新日线',
  };
}

function parseIsoDate(value?: string | null) {
  if (!value) {
    return undefined;
  }
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) {
    return undefined;
  }
  const date = new Date(Date.UTC(year, month - 1, day));
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function toIsoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function shiftIsoDate(value: string, days: number) {
  const date = parseIsoDate(value);
  if (!date) {
    return value;
  }
  date.setUTCDate(date.getUTCDate() + days);
  return toIsoDate(date);
}

function todayIsoDate() {
  return toIsoDate(new Date());
}

function buildDailyBackfillRange(
  dailyQuality?: StockDailyQuality,
  coverage?: StockDailyCoverage,
  rowCount = 0,
): DailyBackfillRange {
  const missingSamples = [
    ...(dailyQuality?.missing_trade_date_samples ?? []),
    ...(coverage?.missing_trade_date_samples ?? []),
  ]
    .filter((date): date is string => Boolean(parseIsoDate(date)))
    .sort();

  if (missingSamples.length) {
    const firstMissingDate = missingSamples[0];
    const latestMissingDate = missingSamples[missingSamples.length - 1];
    return {
      startDate: shiftIsoDate(firstMissingDate, -MISSING_SAMPLE_PADDING_DAYS),
      endDate: shiftIsoDate(latestMissingDate, MISSING_SAMPLE_PADDING_DAYS),
      label: '缺失样例窗口',
      buttonText: '创建补数任务',
    };
  }

  const missingDays = dailyQuality?.missing_trade_days ?? coverage?.missing_trade_days ?? 0;
  const firstDataDate = dailyQuality?.first_data_date ?? coverage?.first_data_date;
  const latestDataDate = dailyQuality?.latest_data_date ?? coverage?.latest_data_date;
  if (missingDays > 0 && firstDataDate && latestDataDate) {
    return {
      startDate: firstDataDate,
      endDate: latestDataDate,
      label: '覆盖窗口补数',
      buttonText: '创建补数任务',
    };
  }

  const endDate = todayIsoDate();
  if (latestDataDate) {
    const nextDate = shiftIsoDate(latestDataDate, 1);
    if (nextDate <= endDate) {
      return {
        startDate: nextDate,
        endDate,
        label: '最新数据后补齐',
        buttonText: '同步最新日线',
      };
    }
  }

  if (rowCount > 0) {
    return {
      startDate: shiftIsoDate(endDate, -DEFAULT_REFRESH_SYNC_DAYS),
      endDate,
      label: '最近 30 天刷新',
      buttonText: '同步最新日线',
    };
  }

  return {
    startDate: shiftIsoDate(endDate, -DEFAULT_INITIAL_SYNC_DAYS),
    endDate,
    label: '最近 90 天初始化',
    buttonText: '同步该股票日线',
  };
}

function buildDataProfile(rows: DailyBar[], total?: number): DataProfile {
  const sortedRows = sortDailyRows(rows);
  const sourceList = [...new Set(sortedRows.map((row) => row.source).filter(Boolean))];
  const adjustTypeList = [...new Set(sortedRows.map((row) => row.adjust_type || 'none'))];
  const ingestedTimes = sortedRows
    .map((row) => row.ingested_at)
    .filter((value): value is string => Boolean(value))
    .sort();

  return {
    rowCount: total ?? rows.length,
    sourceList,
    adjustTypeList,
    firstDate: sortedRows[0]?.trade_date,
    latestDate: sortedRows[sortedRows.length - 1]?.trade_date,
    latestIngestedAt: ingestedTimes[ingestedTimes.length - 1],
  };
}

function buildChartModel(rows: DailyBar[]): ChartModel | null {
  const sortedRows = sortDailyRows(rows);
  if (!sortedRows.length) {
    return null;
  }

  const closes = sortedRows.map((row) => row.close);
  const priceValues = sortedRows.flatMap((row) => [row.open, row.high, row.low, row.close]);
  const maxPrice = Math.max(...priceValues);
  const minPrice = Math.min(...priceValues);
  const priceRange = Math.max(maxPrice - minPrice, Math.abs(maxPrice) * 0.01, 1);
  const upperBound = maxPrice + priceRange * 0.1;
  const lowerBound = minPrice - priceRange * 0.1;
  const plotWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right;
  const plotHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;
  const plotBottom = CHART_HEIGHT - CHART_PADDING.bottom;
  const denominator = upperBound - lowerBound || 1;
  const yForPrice = (value: number) => CHART_PADDING.top + ((upperBound - value) / denominator) * plotHeight;

  const points = sortedRows.map((row, index) => {
    const x =
      CHART_PADDING.left +
      (sortedRows.length === 1 ? plotWidth / 2 : (index / (sortedRows.length - 1)) * plotWidth);
    const y = yForPrice(row.close);
    return { x, y, row };
  });
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${plotBottom} L ${points[0].x} ${plotBottom} Z`;
  const maxVolume = Math.max(...sortedRows.map((row) => row.volume));
  const barWidth = Math.max(6, Math.min(26, plotWidth / Math.max(sortedRows.length * 2.5, 1)));
  const candleWidth = Math.max(4, Math.min(14, plotWidth / Math.max(sortedRows.length * 1.8, 1)));
  const candles = points.map((point) => ({
    x: point.x,
    openY: yForPrice(point.row.open),
    closeY: yForPrice(point.row.close),
    highY: yForPrice(point.row.high),
    lowY: yForPrice(point.row.low),
    width: candleWidth,
    isUp: point.row.close >= point.row.open,
    row: point.row,
  }));
  const volumeBars = points.map((point) => {
    const height = maxVolume > 0 ? Math.max(3, (point.row.volume / maxVolume) * 40) : 0;
    return {
      x: point.x - barWidth / 2,
      y: plotBottom - height,
      width: barWidth,
      height,
      isUp: point.row.close >= point.row.open,
    };
  });

  return {
    rows: sortedRows,
    points,
    candles,
    volumeBars,
    linePath,
    areaPath,
    lowerBound,
    upperBound,
    minPrice,
    maxPrice,
    first: sortedRows[0],
    latest: sortedRows[sortedRows.length - 1],
  };
}

function buildDailyColumns(): ColumnsType<DailyBar> {
  return [
    { title: '交易日', dataIndex: 'trade_date', width: 120, render: (value) => formatDate(value) },
    { title: '开盘', dataIndex: 'open', width: 100, render: (value) => formatDecimal(value) },
    { title: '最高', dataIndex: 'high', width: 100, render: (value) => formatDecimal(value) },
    { title: '最低', dataIndex: 'low', width: 100, render: (value) => formatDecimal(value) },
    {
      title: '收盘',
      dataIndex: 'close',
      width: 100,
      render: (value) => <Typography.Text strong>{formatDecimal(value)}</Typography.Text>,
    },
    { title: '成交量', dataIndex: 'volume', width: 130, render: (value) => formatNumber(value) },
    { title: '成交额', dataIndex: 'amount', width: 140, render: (value) => formatNumber(value) },
    { title: '复权口径', dataIndex: 'adjust_type', width: 110, render: (value) => formatAdjustType(value) },
    { title: '来源', dataIndex: 'source', width: 120 },
    { title: '更新时间', dataIndex: 'ingested_at', width: 180, render: (value) => formatDateTime(value) },
  ];
}

function CloseVolumeChart({ model }: { model: ChartModel | null }) {
  if (!model) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日线数据，先在同步调度中同步该股票日线。" />;
  }

  const isUp = model.latest.close >= model.first.close;
  const ticks = [model.maxPrice, (model.maxPrice + model.minPrice) / 2, model.minPrice];
  const plotHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;
  const priceToY = (value: number) =>
    CHART_PADDING.top + ((model.upperBound - value) / Math.max(model.upperBound - model.lowerBound, 1)) * plotHeight;

  return (
    <div className={`stock-detail-chart ${isUp ? 'is-up' : 'is-down'}`}>
      <div className="stock-detail-chart-meta">
        <Space size={12} wrap>
          <Tag color="blue">K 线</Tag>
          <Tag>收盘趋势</Tag>
          <Tag>成交量</Tag>
          <Typography.Text type="secondary">
            {formatDate(model.first.trade_date)} ~ {formatDate(model.latest.trade_date)}
          </Typography.Text>
        </Space>
      </div>
      <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img" aria-label="单股收盘趋势和成交量">
        <defs>
          <linearGradient id="stockDetailTrendFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {ticks.map((tick) => {
          const y = priceToY(tick);
          return (
            <g key={tick}>
              <line className="stock-detail-grid" x1={CHART_PADDING.left} x2={CHART_WIDTH - CHART_PADDING.right} y1={y} y2={y} />
              <text className="stock-detail-axis" x={CHART_PADDING.left - 10} y={y + 4} textAnchor="end">
                {formatDecimal(tick)}
              </text>
            </g>
          );
        })}
        {model.volumeBars.map((bar, index) => (
          <rect
            key={`${model.rows[index].trade_date}-volume`}
            className={`stock-detail-volume ${bar.isUp ? 'is-up' : 'is-down'}`}
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={bar.height}
            rx={3}
          />
        ))}
        <path className="stock-detail-area" d={model.areaPath} />
        {model.candles.map((candle) => {
          const bodyY = Math.min(candle.openY, candle.closeY);
          const bodyHeight = Math.max(Math.abs(candle.closeY - candle.openY), 2);
          return (
            <g key={`${candle.row.trade_date}-candle`} className={`stock-detail-candle ${candle.isUp ? 'is-up' : 'is-down'}`}>
              <line className="stock-detail-candle-wick" x1={candle.x} x2={candle.x} y1={candle.highY} y2={candle.lowY} />
              <rect
                className="stock-detail-candle-body"
                x={candle.x - candle.width / 2}
                y={bodyY}
                width={candle.width}
                height={bodyHeight}
                rx={1.5}
              >
                <title>
                  {`${formatDate(candle.row.trade_date)} 开 ${formatDecimal(candle.row.open)} 高 ${formatDecimal(candle.row.high)} 低 ${formatDecimal(candle.row.low)} 收 ${formatDecimal(candle.row.close)}`}
                </title>
              </rect>
            </g>
          );
        })}
        <path className="stock-detail-line" d={model.linePath} />
        {model.points.map((point) => (
          <circle key={point.row.trade_date} className="stock-detail-point" cx={point.x} cy={point.y} r={3.2}>
            <title>{`${formatDate(point.row.trade_date)} 收盘 ${formatDecimal(point.row.close)}`}</title>
          </circle>
        ))}
        <text className="stock-detail-axis" x={model.points[0].x} y={CHART_HEIGHT - 8} textAnchor="start">
          {formatDate(model.first.trade_date)}
        </text>
        <text className="stock-detail-axis" x={model.points[model.points.length - 1].x} y={CHART_HEIGHT - 8} textAnchor="end">
          {formatDate(model.latest.trade_date)}
        </text>
      </svg>
    </div>
  );
}

function QualityTags({ summary }: { summary: QualitySummary }) {
  if (!summary.checkedRows) {
    return <Tag>暂无样本</Tag>;
  }

  return (
    <Space wrap size={[8, 8]}>
      <Tag color={summary.duplicateDates ? 'red' : 'green'}>重复日期 {formatNumber(summary.duplicateDates)}</Tag>
      <Tag color={summary.priceErrors ? 'red' : 'green'}>价格异常 {formatNumber(summary.priceErrors)}</Tag>
      <Tag color={summary.missingSampleGaps ? 'warning' : 'green'}>大间隔样本 {formatNumber(summary.missingSampleGaps)}</Tag>
      <Tag color="blue">检查样本 {formatNumber(summary.checkedRows)} 条</Tag>
    </Space>
  );
}

function formatCoveragePercent(value?: number | null) {
  return value === undefined || value === null ? '-' : formatPercent(value * 100);
}

function getBatchTaskId(batch: StockDailyIngestBatch) {
  return batch.task_id ?? batch.taskId;
}

function getBatchDatasetName(batch: StockDailyIngestBatch) {
  return batch.dataset_name ?? batch.datasetName ?? 'daily_bars';
}

function getNumericBatchId(batch: StockDailyIngestBatch) {
  const batchId = Number(batch.id);
  return Number.isFinite(batchId) && batchId > 0 ? batchId : undefined;
}

function getNumericTaskId(batch: StockDailyIngestBatch) {
  const taskId = Number(getBatchTaskId(batch));
  return Number.isFinite(taskId) && taskId > 0 ? taskId : undefined;
}

function getBatchRequestedSource(batch: StockDailyIngestBatch) {
  return batch.requested_source ?? batch.requestedSource;
}

function getBatchRecordsWritten(batch: StockDailyIngestBatch) {
  return batch.records_written ?? batch.recordsWritten ?? 0;
}

function getBatchQualityStatus(batch: StockDailyIngestBatch) {
  return batch.quality_status ?? batch.qualityStatus;
}

function getBatchSchemaVersion(batch: StockDailyIngestBatch) {
  return batch.schema_version ?? batch.schemaVersion ?? '-';
}

function getBatchNormalizeVersion(batch: StockDailyIngestBatch) {
  return batch.normalize_version ?? batch.normalizeVersion ?? '-';
}

function getBatchStartedAt(batch: StockDailyIngestBatch) {
  return batch.started_at ?? batch.startedAt;
}

function getBatchFinishedAt(batch: StockDailyIngestBatch) {
  return batch.finished_at ?? batch.finishedAt;
}

function getBatchCreatedAt(batch: StockDailyIngestBatch) {
  return batch.created_at ?? batch.createdAt;
}

function getBatchErrorMessage(batch: StockDailyIngestBatch) {
  return batch.error_message ?? batch.errorMessage;
}

function getBatchStartDate(batch: StockDailyIngestBatch) {
  return batch.start_date ?? batch.startDate;
}

function getBatchEndDate(batch: StockDailyIngestBatch) {
  return batch.end_date ?? batch.endDate;
}

function formatBatchRange(batch: StockDailyIngestBatch) {
  const startDate = getBatchStartDate(batch);
  const endDate = getBatchEndDate(batch);
  if (!startDate && !endDate) {
    return '-';
  }
  if (startDate && endDate && startDate !== endDate) {
    return `${formatDate(startDate)} ~ ${formatDate(endDate)}`;
  }
  return formatDate(endDate ?? startDate);
}

function batchSortTime(batch: StockDailyIngestBatch) {
  const value = getBatchFinishedAt(batch) ?? getBatchStartedAt(batch) ?? getBatchCreatedAt(batch);
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function getLatestIngestBatch(batches: StockDailyIngestBatch[]) {
  if (!batches.length) {
    return undefined;
  }
  return [...batches].sort((left, right) => batchSortTime(right) - batchSortTime(left))[0];
}

function dailyBarToKLine(row: DailyBar): KLine {
  return {
    date: row.trade_date,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.volume,
  };
}

function getBatchLineageSearch(batch: StockDailyIngestBatch, fallback: { market: string; symbol: string }) {
  const batchId = getNumericBatchId(batch);
  return {
    market: batch.market || fallback.market,
    lineageBatchId: batchId,
    lineageDatasetName: getBatchDatasetName(batch),
    lineageSymbol: batch.symbol || fallback.symbol,
    lineageTradeDate: getBatchEndDate(batch) ?? getBatchStartDate(batch) ?? undefined,
    lineageSource: batch.source || undefined,
    lineageStatus: batch.status || undefined,
    lineagePage: 1,
    lineagePageSize: 8,
  };
}

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
