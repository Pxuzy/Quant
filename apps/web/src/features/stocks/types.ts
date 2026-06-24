export type StockMarket = 'A_SHARE' | 'HK' | 'US';
export type StockStatus = 'LISTED' | 'SUSPENDED' | 'DELISTED';

export type Stock = {
  id?: string | number;
  symbol: string;
  exchange?: string;
  market?: StockMarket | string;
  name: string;
  status?: StockStatus | string;
  industry?: string | null;
  listing_date?: string | null;
  listingDate?: string | null;
  delisting_date?: string | null;
  latest_data_date?: string | null;
  latestDataDate?: string | null;
  data_completeness?: number | null;
  dataCompleteness?: number | null;
  source?: string | null;
  updated_at?: string | null;
  updatedAt?: string | null;
};

export type StockDailyCoverage = {
  symbol: string;
  market: string;
  first_data_date?: string | null;
  latest_data_date?: string | null;
  expected_trade_days: number;
  actual_trade_days: number;
  missing_trade_days: number;
  data_completeness?: number | null;
  missing_trade_date_samples: string[];
};

export type StockDailyQualityStatus = 'good' | 'warning' | 'error' | 'unknown';

export type StockDailyQuality = {
  symbol: string;
  market: string;
  status: StockDailyQualityStatus | string;
  checked_rows: number;
  first_data_date?: string | null;
  latest_data_date?: string | null;
  expected_trade_days: number;
  actual_trade_days: number;
  missing_trade_days: number;
  data_completeness?: number | null;
  missing_trade_date_samples: string[];
  duplicate_daily_keys: number;
  ohlc_error_count: number;
  negative_price_count: number;
  negative_volume_count: number;
  negative_amount_count: number;
  adjust_types: string[];
  sources: string[];
};

export type StockDailyIngestBatch = {
  id: string | number;
  task_id?: string | number;
  taskId?: string | number;
  dataset_name?: string;
  datasetName?: string;
  source: string;
  requested_source?: string;
  requestedSource?: string;
  market?: string | null;
  symbol?: string | null;
  start_date?: string | null;
  startDate?: string | null;
  end_date?: string | null;
  endDate?: string | null;
  status: string;
  schema_version?: string;
  schemaVersion?: string;
  normalize_version?: string;
  normalizeVersion?: string;
  raw_records?: number;
  rawRecords?: number;
  normalized_records?: number;
  normalizedRecords?: number;
  records_written?: number;
  recordsWritten?: number;
  validation_errors_json?: string[];
  validationErrorsJson?: string[];
  error_message?: string | null;
  errorMessage?: string | null;
  quality_status?: string;
  qualityStatus?: string;
  started_at?: string | null;
  startedAt?: string | null;
  finished_at?: string | null;
  finishedAt?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
};

export type StockDailyIngestBatchesResult = {
  symbol: string;
  market: string;
  items: StockDailyIngestBatch[];
  total: number;
};

export type StockListParams = {
  keyword?: string;
  exchange?: string;
  industry?: string;
  market?: string;
  status?: string;
  dailyCoverage?: string;
  page: number;
  pageSize: number;
};

export type StockFilterValues = Pick<
  StockListParams,
  'keyword' | 'exchange' | 'industry' | 'market' | 'status' | 'dailyCoverage'
> & {
  syncSource?: string;
};

export type SyncStocksRequest = {
  source?: string;
  market?: string;
};
