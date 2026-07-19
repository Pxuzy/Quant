export type DatabaseStatus = {
  database_kind: string;
  database_role: string;
  database_note: string;
  database_url: string;
  database_size_bytes?: number | null;
  data_lake_path: string;
  data_lake_size_bytes: number;
  parquet_file_count: number;
  total_file_count: number;
  duckdb_engine_status: string;
  duckdb_engine_note: string;
};

export type DatasetSnapshot = {
  dataset_name: string;
  layer: string;
  storage_type: string;
  source: string;
  row_count: number;
  latest_data_date?: string | null;
  quality_status: string;
  dataset_version: string;
  schema_fields_count: number;
  primary_keys_json: string[];
  partition_keys_json: string[];
  updated_at: string;
};

export type SyncWatermark = {
  dataset_name: string;
  source: string;
  requested_source: string;
  market?: string | null;
  symbol?: string | null;
  latest_success_date?: string | null;
  last_success_at?: string | null;
  records_written: number;
  quality_status: string;
  task_id: string | number;
  batch_id: string | number;
  last_failed_at?: string | null;
  last_failure_reason?: string | null;
  last_failure_task_id?: string | number | null;
  last_failure_batch_id?: string | number | null;
  repair_start_date?: string | null;
  repair_end_date?: string | null;
  repair_reason?: string | null;
};

export type ProviderIntegration = {
  source: string;
  attempts: number;
  successes: number;
  failures: number;
  fallback_successes: number;
  records_written: number;
  last_success_at?: string | null;
  last_failure_at?: string | null;
};

export type RecentIngestBatch = {
  id: string | number;
  task_id: string | number;
  dataset_name: string;
  source: string;
  requested_source: string;
  market?: string | null;
  symbol?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status: string;
  schema_version: string;
  normalize_version: string;
  records_written: number;
  quality_status: string;
  error_message?: string | null;
  started_at: string;
  finished_at?: string | null;
};

export type DatabaseLineageItem = {
  id: string | number;
  task_id: string | number;
  task_type: string;
  task_status: string;
  task_source: string;
  task_error_message?: string | null;
  dataset_name: string;
  source: string;
  requested_source: string;
  market?: string | null;
  symbol?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status: string;
  schema_version: string;
  normalize_version: string;
  raw_records: number;
  normalized_records: number;
  dropped_records: number;
  records_written: number;
  validation_errors_json: string[];
  error_message?: string | null;
  quality_status: string;
  started_at: string;
  finished_at?: string | null;
  created_at: string;
};

export type DatabaseLineageParams = {
  batchId?: number;
  datasetName?: string;
  market?: string;
  symbol?: string;
  tradeDate?: string;
  source?: string;
  status?: string;
  page?: number;
  pageSize?: number;
};

export type DatabaseLineageResult = {
  items: DatabaseLineageItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type DatabaseCoverageSummary = {
  market: string;
  coverage_status: 'ok' | 'degraded' | string;
  coverage_message?: string | null;
  stock_pool_total: number;
  daily_covered_stock_count: number;
  calendar_latest_date?: string | null;
  coverage_start_date?: string | null;
  coverage_end_date?: string | null;
  daily_expected_symbol_days: number;
  daily_actual_symbol_days: number;
  daily_missing_symbol_days: number;
  daily_completeness?: number | null;
};

export type DatabaseIntegrationSummary = {
  datasets_total: number;
  total_rows: number;
  latest_data_date?: string | null;
  recent_batches_total: number;
  failed_batches_total: number;
  fallback_successes_total: number;
  healthy_providers_total: number;
};

export type DatabaseIntegrationOverview = {
  summary: DatabaseIntegrationSummary;
  coverage_summary: DatabaseCoverageSummary;
  dataset_snapshots: DatasetSnapshot[];
  sync_watermarks: SyncWatermark[];
  provider_integrations: ProviderIntegration[];
  recent_batches: RecentIngestBatch[];
};
