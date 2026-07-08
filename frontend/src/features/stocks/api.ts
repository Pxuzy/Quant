import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import { normalizePageResult } from '../../shared/api/pagination';
import type { LoosePage, PageResult } from '../../shared/api/pagination';
import type {
  Stock,
  StockDailyCoverage,
  StockDailyIngestBatchesResult,
  StockDailyQuality,
  StockListParams,
  SyncStocksRequest,
} from './types';
import { syncTaskQueryKeys } from '../sync-tasks/api';
import type { SyncTask } from '../sync-tasks/types';

export const stockQueryKeys = {
  all: ['stocks'] as const,
  list: (params: StockListParams) => [...stockQueryKeys.all, 'list', params] as const,
  detail: (symbol: string, market?: string) => [...stockQueryKeys.all, 'detail', symbol, market] as const,
  dailyCoverage: (symbol: string, market?: string) => [...stockQueryKeys.all, 'daily-coverage', symbol, market] as const,
  dailyQuality: (symbol: string, market?: string) => [...stockQueryKeys.all, 'daily-quality', symbol, market] as const,
  dailyIngestBatches: (symbol: string, market?: string) => [...stockQueryKeys.all, 'daily-ingest-batches', symbol, market] as const,
};

export function fetchStocks(
  params: StockListParams,
  signal?: AbortSignal,
): Promise<PageResult<Stock>> {
  return apiRequest<unknown>(
    '/api/stocks',
    {
      keyword: params.keyword,
      exchange: params.exchange,
      industry: params.industry,
      market: params.market,
      status: params.status,
      daily_coverage: params.dailyCoverage,
      page: params.page,
      page_size: params.pageSize,
    },
    { signal },
  ).then((payload) =>
    normalizePageResult(payload as LoosePage<Stock>, params.page, params.pageSize),
  );
}

export function syncStocks(payload: SyncStocksRequest): Promise<SyncTask> {
  return apiRequest<SyncTask>('/api/stocks/sync', undefined, {
    method: 'POST',
    body: payload,
  });
}

export function fetchStock(symbol: string, market?: string, signal?: AbortSignal): Promise<Stock> {
  return apiRequest<Stock>(`/api/stocks/${symbol}`, { market }, { signal });
}

export function fetchStockDailyCoverage(
  symbol: string,
  market?: string,
  signal?: AbortSignal,
): Promise<StockDailyCoverage> {
  return apiRequest<StockDailyCoverage>(`/api/stocks/${symbol}/daily-coverage`, { market }, { signal });
}

export function fetchStockDailyQuality(
  symbol: string,
  market?: string,
  signal?: AbortSignal,
): Promise<StockDailyQuality> {
  return apiRequest<StockDailyQuality>(`/api/stocks/${symbol}/daily-quality`, { market }, { signal });
}

export function fetchStockDailyIngestBatches(
  symbol: string,
  market?: string,
  signal?: AbortSignal,
): Promise<StockDailyIngestBatchesResult> {
  return apiRequest<StockDailyIngestBatchesResult>(`/api/stocks/${symbol}/daily-ingest-batches`, { market }, { signal });
}

export function useStocksQuery(params: StockListParams) {
  return useQuery({
    queryKey: stockQueryKeys.list(params),
    queryFn: ({ signal }) => fetchStocks(params, signal),
    placeholderData: (previousData) => previousData,
  });
}

export function useStockQuery(symbol: string, market?: string) {
  return useQuery({
    queryKey: stockQueryKeys.detail(symbol, market),
    queryFn: ({ signal }) => fetchStock(symbol, market, signal),
    enabled: Boolean(symbol.trim()),
  });
}

export function useStockDailyCoverageQuery(symbol: string, market?: string) {
  return useQuery({
    queryKey: stockQueryKeys.dailyCoverage(symbol, market),
    queryFn: ({ signal }) => fetchStockDailyCoverage(symbol, market, signal),
    enabled: Boolean(symbol.trim()),
  });
}

export function useStockDailyQualityQuery(symbol: string, market?: string) {
  return useQuery({
    queryKey: stockQueryKeys.dailyQuality(symbol, market),
    queryFn: ({ signal }) => fetchStockDailyQuality(symbol, market, signal),
    enabled: Boolean(symbol.trim()),
  });
}

export function useStockDailyIngestBatchesQuery(symbol: string, market?: string) {
  return useQuery({
    queryKey: stockQueryKeys.dailyIngestBatches(symbol, market),
    queryFn: ({ signal }) => fetchStockDailyIngestBatches(symbol, market, signal),
    enabled: Boolean(symbol.trim()),
  });
}

export function useSyncStocksMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: syncStocks,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: stockQueryKeys.all });
      void queryClient.refetchQueries({ queryKey: syncTaskQueryKeys.all, type: 'active' });
    },
  });
}
