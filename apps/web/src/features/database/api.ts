import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import type {
  DatabaseIntegrationOverview,
  DatabaseLineageParams,
  DatabaseLineageResult,
  DatabaseStatus,
} from './types';

export type DatabaseIntegrationOverviewParams = {
  market?: string;
};

type QueryOptions = {
  enabled?: boolean;
};

export const databaseQueryKeys = {
  all: ['database'] as const,
  status: () => [...databaseQueryKeys.all, 'status'] as const,
  integrationOverview: (params: DatabaseIntegrationOverviewParams = {}) =>
    [...databaseQueryKeys.all, 'integration-overview', params] as const,
  lineage: (params: DatabaseLineageParams = {}) => [...databaseQueryKeys.all, 'lineage', params] as const,
};

export function fetchDatabaseStatus(signal?: AbortSignal): Promise<DatabaseStatus> {
  return apiRequest<DatabaseStatus>('/api/database/status', undefined, { signal });
}

export function fetchDatabaseIntegrationOverview(
  params: DatabaseIntegrationOverviewParams = {},
  signal?: AbortSignal,
): Promise<DatabaseIntegrationOverview> {
  return apiRequest<DatabaseIntegrationOverview>(
    '/api/database/integration-overview',
    {
      market: params.market,
    },
    { signal },
  );
}

export function fetchDatabaseLineage(
  params: DatabaseLineageParams = {},
  signal?: AbortSignal,
): Promise<DatabaseLineageResult> {
  return apiRequest<DatabaseLineageResult>(
    '/api/database/lineage',
    {
      batch_id: params.batchId,
      dataset_name: params.datasetName,
      market: params.market,
      symbol: params.symbol,
      trade_date: params.tradeDate,
      source: params.source,
      status: params.status,
      page: params.page,
      page_size: params.pageSize,
    },
    { signal },
  );
}

export function useDatabaseStatusQuery() {
  return useQuery({
    queryKey: databaseQueryKeys.status(),
    queryFn: ({ signal }) => fetchDatabaseStatus(signal),
  });
}

export function useDatabaseIntegrationOverviewQuery(params: DatabaseIntegrationOverviewParams = {}) {
  return useQuery({
    queryKey: databaseQueryKeys.integrationOverview(params),
    queryFn: ({ signal }) => fetchDatabaseIntegrationOverview(params, signal),
  });
}

export function useDatabaseLineageQuery(params: DatabaseLineageParams = {}, options: QueryOptions = {}) {
  return useQuery({
    queryKey: databaseQueryKeys.lineage(params),
    queryFn: ({ signal }) => fetchDatabaseLineage(params, signal),
    enabled: options.enabled ?? true,
    placeholderData: (previousData) => previousData,
  });
}
