import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import type {
  DataSource,
  DataSourceCatalogItem,
  DataSourceHealthResult,
  DataSourceSmokeResult,
  DataSourceUpdate,
} from './types';

export const dataSourceQueryKeys = {
  all: ['data-sources'] as const,
  list: () => [...dataSourceQueryKeys.all, 'list'] as const,
  catalog: () => [...dataSourceQueryKeys.all, 'catalog'] as const,
};

export function fetchDataSources(signal?: AbortSignal): Promise<DataSource[]> {
  return apiRequest<DataSource[]>('/api/data-sources', undefined, { signal });
}

export function fetchDataSourceCatalog(signal?: AbortSignal): Promise<DataSourceCatalogItem[]> {
  return apiRequest<DataSourceCatalogItem[]>('/api/data-sources/catalog', undefined, { signal });
}

export function updateDataSource(code: string, payload: DataSourceUpdate): Promise<DataSource> {
  return apiRequest<DataSource>(`/api/data-sources/${code}`, undefined, {
    method: 'PATCH',
    body: payload,
  });
}

export function checkDataSourceHealth(code: string): Promise<DataSourceHealthResult> {
  return apiRequest<DataSourceHealthResult>(`/api/data-sources/${code}/health-check`, undefined, {
    method: 'POST',
  });
}

export function smokeTestDataSource({
  code,
  capability,
}: {
  code: string;
  capability?: string;
}): Promise<DataSourceSmokeResult> {
  const query = capability ? `?capability=${encodeURIComponent(capability)}` : '';
  return apiRequest<DataSourceSmokeResult>(`/api/data-sources/${code}/smoke-test${query}`, undefined, {
    method: 'POST',
  });
}

export function useDataSourcesQuery() {
  return useQuery({
    queryKey: dataSourceQueryKeys.list(),
    queryFn: ({ signal }) => fetchDataSources(signal),
  });
}

export function useDataSourceCatalogQuery() {
  return useQuery({
    queryKey: dataSourceQueryKeys.catalog(),
    queryFn: ({ signal }) => fetchDataSourceCatalog(signal),
  });
}

export function useUpdateDataSourceMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ code, payload }: { code: string; payload: DataSourceUpdate }) => updateDataSource(code, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dataSourceQueryKeys.all });
    },
  });
}

export function useCheckDataSourceHealthMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: checkDataSourceHealth,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dataSourceQueryKeys.all });
    },
  });
}

export function useSmokeTestDataSourceMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: smokeTestDataSource,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dataSourceQueryKeys.all });
    },
  });
}
