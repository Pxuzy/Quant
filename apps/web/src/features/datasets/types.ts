export type Dataset = {
  id: string | number;
  name: string;
  layer: string;
  storage_type: string;
  path?: string | null;
  schema_json: Record<string, string>;
  primary_keys_json: string[];
  partition_keys_json: string[];
  source: string;
  row_count: number;
  latest_data_date?: string | null;
  quality_status: string;
  updated_at?: string | null;
};

export type DatasetListParams = {
  name?: string;
  layer?: string;
  storageType?: string;
  page: number;
  pageSize: number;
};
