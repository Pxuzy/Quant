import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import { normalizePageResult } from '../../shared/api/pagination';
import type { LoosePage, PageResult } from '../../shared/api/pagination';
import { datasetQueryKeys } from '../datasets/api';
import { syncTaskQueryKeys } from '../sync-tasks/api';
import type { SyncTask } from '../sync-tasks/types';
import type {
  DailyBar,
  DailyBarsListParams,
  DailyBarsMarketRepairPreviewResponse,
  DailyBarsMarketRepairRequest,
  DailyBarsSyncRequest,
} from './types';

export const marketDataQueryKeys = {
  all: ['market-data'] as const,
  dailyBars: (params: DailyBarsListParams) => [...marketDataQueryKeys.all, 'daily-bars', params] as const,
};

export function fetchDailyBars(
  params: DailyBarsListParams,
  signal?: AbortSignal,
): Promise<PageResult<DailyBar>> {
  return apiRequest<unknown>(
    '/api/market-data/daily-bars',
    {
      symbol: params.symbol,
      market: params.market,
      start_date: params.startDate,
      end_date: params.endDate,
      sort_order: params.sortOrder,
      page: params.page,
      page_size: params.pageSize,
    },
    { signal },
  ).then((payload) =>
    normalizePageResult(payload as LoosePage<DailyBar>, params.page, params.pageSize),
  );
}

export function syncDailyBars(payload: DailyBarsSyncRequest): Promise<SyncTask> {
  return apiRequest<SyncTask>('/api/market-data/daily-bars/sync', undefined, {
    method: 'POST',
    body: payload,
  });
}

export function syncDailyBarsMarketRepair(payload: DailyBarsMarketRepairRequest): Promise<SyncTask> {
  return apiRequest<SyncTask>('/api/market-data/daily-bars/market-repair', undefined, {
    method: 'POST',
    body: payload,
  });
}

export function previewDailyBarsMarketRepair(
  payload: DailyBarsMarketRepairRequest,
): Promise<DailyBarsMarketRepairPreviewResponse> {
  return apiRequest<DailyBarsMarketRepairPreviewResponse>(
    '/api/market-data/daily-bars/market-repair/preview',
    undefined,
    {
      method: 'POST',
      body: payload,
    },
  );
}

export function useDailyBarsQuery(params: DailyBarsListParams) {
  return useQuery({
    queryKey: marketDataQueryKeys.dailyBars(params),
    queryFn: ({ signal }) => fetchDailyBars(params, signal),
    enabled: Boolean(params.symbol?.trim()),
    placeholderData: (previousData) => previousData,
  });
}

export function useSyncDailyBarsMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: syncDailyBars,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketDataQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: datasetQueryKeys.all });
      void queryClient.refetchQueries({ queryKey: syncTaskQueryKeys.all, type: 'active' });
    },
  });
}

export function useSyncDailyBarsMarketRepairMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: syncDailyBarsMarketRepair,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketDataQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: datasetQueryKeys.all });
      void queryClient.refetchQueries({ queryKey: syncTaskQueryKeys.all, type: 'active' });
    },
  });
}

export function usePreviewDailyBarsMarketRepairMutation() {
  return useMutation({
    mutationFn: previewDailyBarsMarketRepair,
  });
}
