import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import { normalizePageResult } from '../../shared/api/pagination';
import type { LoosePage } from '../../shared/api/pagination';
import { datasetQueryKeys } from '../datasets/api';
import type {
  DataQualityCheckResult,
  DataQualityCheckRun,
  DataQualityOverview,
  DataQualityReport,
  DataQualityReportPage,
  DataQualityReportListParams,
} from './types';

type QueryOptions = {
  enabled?: boolean;
};

export const dataQualityQueryKeys = {
  all: ['data-quality'] as const,
  overview: () => [...dataQualityQueryKeys.all, 'overview'] as const,
  reports: (params: DataQualityReportListParams) => [...dataQualityQueryKeys.all, 'reports', params] as const,
  checkRuns: () => [...dataQualityQueryKeys.all, 'check-runs'] as const,
};

export function fetchDataQualityOverview(signal?: AbortSignal): Promise<DataQualityOverview> {
  return apiRequest<DataQualityOverview>('/api/data-quality/overview', undefined, { signal });
}

export function fetchDataQualityReports(
  params: DataQualityReportListParams,
  signal?: AbortSignal,
): Promise<DataQualityReportPage> {
  return apiRequest<unknown>(
    '/api/data-quality/reports',
    {
      dataset_name: params.datasetName,
      status: params.status,
      severity: params.severity,
      checked_at: params.checkedAt,
      page: params.page,
      page_size: params.pageSize,
    },
    { signal },
  ).then((payload) => {
    const loosePayload = payload as LoosePage<DataQualityReport> & { checked_at?: string | null };
    return {
      ...normalizePageResult(loosePayload, params.page, params.pageSize),
      checked_at: loosePayload.checked_at,
    };
  });
}

export function fetchDataQualityCheckRuns(signal?: AbortSignal): Promise<DataQualityCheckRun[]> {
  return apiRequest<{ items: DataQualityCheckRun[] }>('/api/data-quality/check-runs', undefined, { signal }).then(
    (payload) => payload.items,
  );
}

export function runDataQualityCheck(): Promise<DataQualityCheckResult> {
  return apiRequest<DataQualityCheckResult>('/api/data-quality/check', undefined, {
    method: 'POST',
  });
}

export function useDataQualityOverviewQuery() {
  return useQuery({
    queryKey: dataQualityQueryKeys.overview(),
    queryFn: ({ signal }) => fetchDataQualityOverview(signal),
  });
}

export function useDataQualityReportsQuery(params: DataQualityReportListParams, options: QueryOptions = {}) {
  return useQuery({
    queryKey: dataQualityQueryKeys.reports(params),
    queryFn: ({ signal }) => fetchDataQualityReports(params, signal),
    enabled: options.enabled ?? true,
    placeholderData: (previousData) => previousData,
  });
}

export function useDataQualityCheckRunsQuery(options: QueryOptions = {}) {
  return useQuery({
    queryKey: dataQualityQueryKeys.checkRuns(),
    queryFn: ({ signal }) => fetchDataQualityCheckRuns(signal),
    enabled: options.enabled ?? true,
  });
}

export function useRunDataQualityCheckMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: runDataQualityCheck,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dataQualityQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: datasetQueryKeys.all });
    },
  });
}
