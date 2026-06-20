export type DataQualityOverview = {
  datasets_total: number;
  datasets_good: number;
  datasets_warning: number;
  datasets_error: number;
  datasets_unknown: number;
  reports_total: number;
  reports_warning: number;
  reports_error: number;
  latest_checked_at?: string | null;
};

export type DataQualityReportTrace = {
  dataset_source?: string | null;
  storage_type?: string | null;
  row_count?: number | null;
  latest_data_date?: string | null;
  quality_status?: string | null;
  schema_fields_count?: number | null;
  primary_keys_json: string[];
  partition_keys_json: string[];
  latest_batch_id?: string | number | null;
  latest_task_id?: string | number | null;
  latest_batch_source?: string | null;
  latest_batch_requested_source?: string | null;
  latest_batch_market?: string | null;
  latest_batch_symbol?: string | null;
  latest_batch_start_date?: string | null;
  latest_batch_end_date?: string | null;
  latest_batch_status?: string | null;
  latest_batch_schema_version?: string | null;
  latest_batch_normalize_version?: string | null;
  latest_batch_records_written?: number | null;
  latest_batch_quality_status?: string | null;
  latest_batch_finished_at?: string | null;
};

export type DataQualityReport = {
  id: string | number;
  dataset_name: string;
  check_type: string;
  status: string;
  severity: string;
  metric_name: string;
  metric_value?: string | null;
  expected_value?: string | null;
  message: string;
  checked_at: string;
  trace?: DataQualityReportTrace | null;
};

export type DataQualityReportListParams = {
  datasetName?: string;
  status?: string;
  severity?: string;
  checkedAt?: string;
  page: number;
  pageSize: number;
};

export type DataQualityCheckRun = {
  checked_at: string;
  reports_total: number;
  reports_warning: number;
  reports_error: number;
};

export type DataQualityReportPage = {
  items: DataQualityReport[];
  total: number;
  page: number;
  pageSize: number;
  checked_at?: string | null;
};

export type DataQualityCheckResult = {
  checked_datasets: number;
  reports_created: number;
  checked_at: string;
  overview: DataQualityOverview;
};
