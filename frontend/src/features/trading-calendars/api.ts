import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import { normalizePageResult } from '../../shared/api/pagination';
import type { LoosePage, PageResult } from '../../shared/api/pagination';
import { datasetQueryKeys } from '../datasets/api';
import { syncTaskQueryKeys } from '../sync-tasks/api';
import type { SyncTask } from '../sync-tasks/types';
import type { TradingCalendarDay, TradingCalendarListParams, TradingCalendarSyncRequest } from './types';

export const tradingCalendarQueryKeys = {
  all: ['trading-calendars'] as const,
  list: (params: TradingCalendarListParams) => [...tradingCalendarQueryKeys.all, 'list', params] as const,
};

type QueryOptions = {
  enabled?: boolean;
};

function openStatusToQuery(value?: string) {
  if (value === 'open') {
    return 'true';
  }
  if (value === 'closed') {
    return 'false';
  }
  return undefined;
}

export function fetchTradingCalendars(
  params: TradingCalendarListParams,
  signal?: AbortSignal,
): Promise<PageResult<TradingCalendarDay>> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 31;

  return apiRequest<unknown>(
    '/api/trading-calendars',
    {
      market: params.market,
      start_date: params.startDate,
      end_date: params.endDate,
      is_open: openStatusToQuery(params.openStatus),
      page,
      page_size: pageSize,
    },
    { signal },
  ).then((payload) =>
    normalizePageResult(payload as LoosePage<TradingCalendarDay>, page, pageSize),
  );
}

export function syncTradingCalendars(payload: TradingCalendarSyncRequest): Promise<SyncTask> {
  return apiRequest<SyncTask>('/api/trading-calendars/sync', undefined, {
    method: 'POST',
    body: payload,
  });
}

export function useTradingCalendarsQuery(params: TradingCalendarListParams, options: QueryOptions = {}) {
  return useQuery({
    queryKey: tradingCalendarQueryKeys.list(params),
    queryFn: ({ signal }) => fetchTradingCalendars(params, signal),
    enabled: options.enabled ?? true,
    placeholderData: (previousData) => previousData,
  });
}

export function useSyncTradingCalendarsMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: syncTradingCalendars,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tradingCalendarQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: datasetQueryKeys.all });
      void queryClient.refetchQueries({ queryKey: syncTaskQueryKeys.all, type: 'active' });
    },
  });
}
