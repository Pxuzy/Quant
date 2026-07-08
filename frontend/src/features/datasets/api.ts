import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../shared/api/client';
import { normalizePageResult } from '../../shared/api/pagination';
import type { LoosePage, PageResult } from '../../shared/api/pagination';
import type { Dataset, DatasetListParams } from './types';

export const datasetQueryKeys = {
  all: ['datasets'] as const,
  list: (params: DatasetListParams) => [...datasetQueryKeys.all, 'list', params] as const,
  detail: (name?: string | null) => [...datasetQueryKeys.all, 'detail', name] as const,
};

export function fetchDatasets(
  params: DatasetListParams,
  signal?: AbortSignal,
): Promise<PageResult<Dataset>> {
  return apiRequest<unknown>(
    '/api/datasets',
    {
      name: params.name,
      layer: params.layer,
      storage_type: params.storageType,
      page: params.page,
      page_size: params.pageSize,
    },
    { signal },
  ).then((payload) =>
    normalizePageResult(payload as LoosePage<Dataset>, params.page, params.pageSize),
  );
}

export function fetchDataset(name: string, signal?: AbortSignal): Promise<Dataset> {
  return apiRequest<Dataset>(`/api/datasets/${name}`, undefined, { signal });
}

export function useDatasetsQuery(params: DatasetListParams) {
  return useQuery({
    queryKey: datasetQueryKeys.list(params),
    queryFn: ({ signal }) => fetchDatasets(params, signal),
    placeholderData: (previousData) => previousData,
  });
}
