export type SyncTaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'canceled';

export type SyncTask = {
  id: string | number;
  task_type?: string;
  taskType?: string;
  source?: string | null;
  market?: string | null;
  symbol?: string | null;
  status: SyncTaskStatus | string;
  progress?: number | null;
  records_read?: number | null;
  recordsRead?: number | null;
  records_written?: number | null;
  recordsWritten?: number | null;
  candidate_sources?: string[] | null;
  candidateSources?: string[] | null;
  selected_source?: string | null;
  selectedSource?: string | null;
  error_message?: string | null;
  errorMessage?: string | null;
  started_at?: string | null;
  startedAt?: string | null;
  finished_at?: string | null;
  finishedAt?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
};

export type SyncTaskLog = {
  id: string | number;
  task_id?: string | number;
  taskId?: string | number;
  level: string;
  message: string;
  payload_json?: Record<string, unknown> | null;
  payloadJson?: Record<string, unknown> | null;
  created_at?: string | null;
  createdAt?: string | null;
};

export type IngestBatch = {
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

export type SyncTaskLogsResult = {
  task_id?: string | number;
  taskId?: string | number;
  items: SyncTaskLog[];
  total: number;
};

export type SyncTaskIngestBatchesResult = {
  task_id?: string | number;
  taskId?: string | number;
  items: IngestBatch[];
  total: number;
};

export type SyncSchedule = {
  id: string | number;
  code: string;
  name: string;
  task_type: string;
  taskType?: string;
  source: string;
  market?: string | null;
  symbol?: string | null;
  cron_expression: string;
  cronExpression?: string;
  enabled: boolean;
  schedule_note: string;
  scheduleNote?: string;
  last_triggered_at?: string | null;
  lastTriggeredAt?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
  updated_at?: string | null;
  updatedAt?: string | null;
};

export type SyncSchedulesResult = {
  items: SyncSchedule[];
  total: number;
};

export type SyncRunnerTaskRef = {
  id?: string | number | null;
  task_type?: string | null;
  taskType?: string | null;
  status?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
  started_at?: string | null;
  startedAt?: string | null;
  finished_at?: string | null;
  finishedAt?: string | null;
};

export type SyncRunnerStatus = {
  mode: string;
  status: 'idle' | 'pending' | 'running' | 'warning' | string;
  message: string;
  worker_command?: string;
  worker_note?: string;
  supported_task_types?: string[];
  pending_count: number;
  running_count: number;
  failed_count: number;
  success_count: number;
  enabled_schedules: number;
  total_schedules: number;
  latest_task_id?: string | number | null;
  latest_task_status?: string | null;
  latest_task_created_at?: string | null;
  latest_triggered_at?: string | null;
  current_task?: SyncRunnerTaskRef;
  next_pending_task?: SyncRunnerTaskRef;
  latest_success_task?: SyncRunnerTaskRef;
  latest_failed_task?: SyncRunnerTaskRef;
  latest_worker_activity_at?: string | null;
};

export type SyncScheduleUpdate = {
  enabled?: boolean;
  cron_expression?: string;
  source?: string;
  market?: string;
  symbol?: string;
};

export type SyncTaskListParams = {
  page?: number;
  pageSize?: number;
  status?: string;
  source?: string;
  taskType?: string;
  market?: string;
  symbol?: string;
  startDate?: string;
  endDate?: string;
};
