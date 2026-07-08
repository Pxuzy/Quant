// Extracted from StockDetailPage — constants, types, and pure utility functions
import type { DailyBar } from '../../../../features/market-data/types';
import type { KLine } from '../../../../features/market/api';
import type { StockDailyCoverage, StockDailyIngestBatch, StockDailyQuality } from '../../../../features/stocks/types';
import { formatDate, formatNumber, formatPercent } from '../../../../shared/components/formatters';

export const DETAIL_DAILY_PAGE_SIZE = 1000;
export const TABLE_PREVIEW_SIZE = 20;
export const V1_MARKET = 'A_SHARE';
export const DETAIL_KLINE_HISTORY_LIMIT = 30000;
export const CHART_WIDTH = 820;
export const CHART_HEIGHT = 260;
export const CHART_PADDING = { top: 18, right: 28, bottom: 34, left: 54 };
export const DATE_DAY_MS = 86_400_000;
export const MISSING_SAMPLE_PADDING_DAYS = 3;
export const DEFAULT_INITIAL_SYNC_DAYS = 90;
export const DEFAULT_REFRESH_SYNC_DAYS = 30;


export type IndicatorSummary = {
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

export type QualitySummary = {
  duplicateDates: number;
  priceErrors: number;
  missingSampleGaps: number;
  checkedRows: number;
};

export type DataProfile = {
  rowCount: number;
  sourceList: string[];
  adjustTypeList: string[];
  firstDate?: string;
  latestDate?: string;
  latestIngestedAt?: string;
};

export type DailyBackfillRange = {
  startDate: string;
  endDate: string;
  label: string;
  buttonText: string;
};

export type StockQualityDecision = {
  status: string;
  title: string;
  description: string;
  actionLabel: string;
};

export type ChartPoint = {
  x: number;
  y: number;
  row: DailyBar;
};

export type CandleBar = {
  x: number;
  openY: number;
  closeY: number;
  highY: number;
  lowY: number;
  width: number;
  isUp: boolean;
  row: DailyBar;
};

export type VolumeBar = {
  x: number;
  y: number;
  width: number;
  height: number;
  isUp: boolean;
};

export type ChartModel = {
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


export function sortDailyRows(rows: DailyBar[]) {
  return [...rows].sort((a, b) => a.trade_date.localeCompare(b.trade_date));
}

export function normalizeV1Market(market?: string) {
  return market === V1_MARKET ? market : V1_MARKET;
}

export function normalizeStockRouteSymbol(symbol: string) {
  return symbol.replace(/^(sh|sz|bj)/i, '');
}

export function average(values: number[]) {
  if (!values.length) {
    return undefined;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function movingAverage(rows: DailyBar[], windowSize: number) {
  if (rows.length < windowSize) {
    return undefined;
  }
  return average(rows.slice(-windowSize).map((row) => row.close));
}

export function buildIndicatorSummary(rows: DailyBar[]): IndicatorSummary {
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

export function buildQualitySummary(rows: DailyBar[]): QualitySummary {
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

export function getStockQualityDecision({
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

export function parseIsoDate(value?: string | null) {
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

export function toIsoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

export function shiftIsoDate(value: string, days: number) {
  const date = parseIsoDate(value);
  if (!date) {
    return value;
  }
  date.setUTCDate(date.getUTCDate() + days);
  return toIsoDate(date);
}

export function todayIsoDate() {
  return toIsoDate(new Date());
}

export function buildDailyBackfillRange(
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

export function buildDataProfile(rows: DailyBar[], total?: number): DataProfile {
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

export function buildChartModel(rows: DailyBar[]): ChartModel | null {
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


export function formatCoveragePercent(value?: number | null) {
  return value === undefined || value === null ? '-' : formatPercent(value * 100);
}

export function getBatchTaskId(batch: StockDailyIngestBatch) {
  return batch.task_id ?? batch.taskId;
}

export function getBatchDatasetName(batch: StockDailyIngestBatch) {
  return batch.dataset_name ?? batch.datasetName ?? 'daily_bars';
}

export function getNumericBatchId(batch: StockDailyIngestBatch) {
  const batchId = Number(batch.id);
  return Number.isFinite(batchId) && batchId > 0 ? batchId : undefined;
}

export function getNumericTaskId(batch: StockDailyIngestBatch) {
  const taskId = Number(getBatchTaskId(batch));
  return Number.isFinite(taskId) && taskId > 0 ? taskId : undefined;
}

export function getBatchRequestedSource(batch: StockDailyIngestBatch) {
  return batch.requested_source ?? batch.requestedSource;
}

export function getBatchRecordsWritten(batch: StockDailyIngestBatch) {
  return batch.records_written ?? batch.recordsWritten ?? 0;
}


export function getBatchErrorMessage(batch: StockDailyIngestBatch) {
  return batch.error_message ?? batch.errorMessage;
}

export function getBatchFinishedAt(batch: StockDailyIngestBatch) {
  return batch.finished_at ?? batch.finishedAt;
}

export function getBatchStartedAt(batch: StockDailyIngestBatch) {
  return batch.started_at ?? batch.startedAt;
}

export function getBatchCreatedAt(batch: StockDailyIngestBatch) {
  return batch.created_at ?? batch.createdAt;
}

export function getBatchQualityStatus(batch: StockDailyIngestBatch) {
  return batch.quality_status ?? batch.qualityStatus;
}

export function getBatchSchemaVersion(batch: StockDailyIngestBatch) {
  return batch.schema_version ?? batch.schemaVersion;
}

export function getBatchNormalizeVersion(batch: StockDailyIngestBatch) {
  return batch.normalize_version ?? batch.normalizeVersion;
}

export function getBatchStartDate(batch: StockDailyIngestBatch) {
  return batch.start_date ?? batch.startDate;
}

export function getBatchEndDate(batch: StockDailyIngestBatch) {
  return batch.end_date ?? batch.endDate;
}

export function formatBatchRange(batch: StockDailyIngestBatch) {
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

export function batchSortTime(batch: StockDailyIngestBatch) {
  const value = getBatchFinishedAt(batch) ?? getBatchStartedAt(batch) ?? getBatchCreatedAt(batch);
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function getLatestIngestBatch(batches: StockDailyIngestBatch[]) {
  if (!batches.length) {
    return undefined;
  }
  return [...batches].sort((left, right) => batchSortTime(right) - batchSortTime(left))[0];
}

export function dailyBarToKLine(row: DailyBar): KLine {
  return {
    date: row.trade_date,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.volume,
  };
}

export function getBatchLineageSearch(batch: StockDailyIngestBatch, fallback: { market: string; symbol: string }) {
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
