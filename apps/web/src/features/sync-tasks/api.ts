import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import { normalizePageResult } from '../../shared/api/pagination';
import type { LoosePage, PageResult } from '../../shared/api/pagination';
import type {
  SyncSchedule,
  SyncRunnerStatus,
  SyncSchedulesResult,
  SyncScheduleUpdate,
  SyncTask,
  SyncTaskIngestBatchesResult,
  SyncTaskListParams,
  SyncTaskLogsResult,
} from './types';

type DetailQueryOptions = {
  refetchWhenActive?: boolean;
};

type ChildQueryOptions = {
  active?: boolean;
};

function isTaskActive(status?: string) {
  return status === 'pending' || status === 'running';
}

export const syncTaskQueryKeys = {
  all: ['sync-tasks'] as const,
  list: (params: SyncTaskListParams) => [...syncTaskQueryKeys.all, 'list', params] as const,
  detail: (id?: string | number | null) => [...syncTaskQueryKeys.all, 'detail', id] as const,
  logs: (id?: string | number | null) => [...syncTaskQueryKeys.all, 'logs', id] as const,
  ingestBatches: (id?: string | number | null) => [...syncTaskQueryKeys.all, 'ingest-batches', id] as const,
  runnerStatus: () => [...syncTaskQueryKeys.all, 'runner-status'] as const,
  schedules: () => [...syncTaskQueryKeys.all, 'schedules'] as const,
};

export function fetchSyncTasks(
  params: SyncTaskListParams,
  signal?: AbortSignal,
): Promise<PageResult<SyncTask>> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 8;

  return apiRequest<unknown>(
    '/api/sync-tasks',
    {
      page,
      page_size: pageSize,
      status: params.status,
      source: params.source,
      task_type: params.taskType,
      market: params.market,
      symbol: params.symbol,
      start_date: params.startDate,
      end_date: params.endDate,
    },
    { signal },
  ).then((payload) =>
    normalizePageResult(payload as LoosePage<SyncTask>, page, pageSize),
  );
}

export function fetchSyncTask(
  taskId: string | number,
  signal?: AbortSignal,
): Promise<SyncTask> {
  return apiRequest<SyncTask>(`/api/sync-tasks/${taskId}`, undefined, { signal });
}

export function fetchSyncTaskLogs(
  taskId: string | number,
  signal?: AbortSignal,
): Promise<SyncTaskLogsResult> {
  return apiRequest<SyncTaskLogsResult>(`/api/sync-tasks/${taskId}/logs`, undefined, {
    signal,
  });
}

export function fetchSyncTaskIngestBatches(
  taskId: string | number,
  signal?: AbortSignal,
): Promise<SyncTaskIngestBatchesResult> {
  return apiRequest<SyncTaskIngestBatchesResult>(`/api/sync-tasks/${taskId}/ingest-batches`, undefined, {
    signal,
  });
}

export function fetchSyncSchedules(signal?: AbortSignal): Promise<SyncSchedulesResult> {
  return apiRequest<SyncSchedulesResult>('/api/sync-tasks/schedules', undefined, { signal });
}

export function fetchSyncRunnerStatus(signal?: AbortSignal): Promise<SyncRunnerStatus> {
  return apiRequest<SyncRunnerStatus>('/api/sync-tasks/runner-status', undefined, { signal });
}

export function updateSyncSchedule(code: string, payload: SyncScheduleUpdate): Promise<SyncSchedule> {
  return apiRequest<SyncSchedule>(`/api/sync-tasks/schedules/${code}`, undefined, {
    method: 'PATCH',
    body: payload,
  });
}

export function triggerSyncSchedule(code: string): Promise<SyncTask> {
  return apiRequest<SyncTask>(`/api/sync-tasks/schedules/${code}/trigger`, undefined, {
    method: 'POST',
  });
}

export function useSyncTasksQuery(params: SyncTaskListParams = {}) {
  return useQuery({
    queryKey: syncTaskQueryKeys.list(params),
    queryFn: ({ signal }) => fetchSyncTasks(params, signal),
    refetchInterval: (query) => {
      const tasks = query.state.data?.items ?? [];
      return tasks.some((task) => task.status === 'pending' || task.status === 'running')
        ? 5000
        : false;
    },
  });
}

export function useSyncTaskQuery(taskId?: string | number | null, options: DetailQueryOptions = {}) {
  return useQuery({
    queryKey: syncTaskQueryKeys.detail(taskId),
    queryFn: ({ signal }) => fetchSyncTask(taskId as string | number, signal),
    enabled: taskId !== undefined && taskId !== null && taskId !== '',
    refetchInterval: options.refetchWhenActive
      ? (query) => (isTaskActive(query.state.data?.status) ? 3000 : false)
      : false,
  });
}

export function useSyncTaskLogsQuery(taskId?: string | number | null, options: ChildQueryOptions = {}) {
  return useQuery({
    queryKey: syncTaskQueryKeys.logs(taskId),
    queryFn: ({ signal }) => fetchSyncTaskLogs(taskId as string | number, signal),
    enabled: taskId !== undefined && taskId !== null && taskId !== '',
    refetchInterval: options.active ? 3000 : false,
  });
}

export function useSyncTaskIngestBatchesQuery(taskId?: string | number | null, options: ChildQueryOptions = {}) {
  return useQuery({
    queryKey: syncTaskQueryKeys.ingestBatches(taskId),
    queryFn: ({ signal }) => fetchSyncTaskIngestBatches(taskId as string | number, signal),
    enabled: taskId !== undefined && taskId !== null && taskId !== '',
    refetchInterval: options.active ? 3000 : false,
  });
}

export function useSyncSchedulesQuery() {
  return useQuery({
    queryKey: syncTaskQueryKeys.schedules(),
    queryFn: ({ signal }) => fetchSyncSchedules(signal),
  });
}

export function useSyncRunnerStatusQuery() {
  return useQuery({
    queryKey: syncTaskQueryKeys.runnerStatus(),
    queryFn: ({ signal }) => fetchSyncRunnerStatus(signal),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'running' ? 5000 : false;
    },
  });
}

export function useUpdateSyncScheduleMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ code, payload }: { code: string; payload: SyncScheduleUpdate }) => updateSyncSchedule(code, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: syncTaskQueryKeys.schedules() });
      void queryClient.invalidateQueries({ queryKey: syncTaskQueryKeys.runnerStatus() });
    },
  });
}

export function useTriggerSyncScheduleMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ code }: { code: string }) => triggerSyncSchedule(code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: syncTaskQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: syncTaskQueryKeys.schedules() });
      void queryClient.invalidateQueries({ queryKey: syncTaskQueryKeys.runnerStatus() });
    },
  });
}
