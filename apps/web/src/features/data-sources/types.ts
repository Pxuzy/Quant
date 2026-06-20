export type DataSourceCapability = {
  stock_list?: boolean;
  daily_bars?: boolean;
  calendars?: boolean;
  daily_bar_exchanges?: string[] | null;
};

export type DataSourceProviderMetadata = {
  provider_type?: string;
  homepage_url?: string | null;
  docs_url?: string | null;
  auth_mode?: string;
  stability?: string;
  rate_limit_note?: string | null;
  install_note?: string | null;
};

export type DataSourceSmokeSummary = {
  checked_at?: string;
  healthy?: boolean;
  status?: string;
  message?: string;
  capability?: string;
  raw_records?: number;
  normalized_records?: number;
  validation_errors?: string[];
  sample?: Array<Record<string, unknown>>;
};

export type DataSource = {
  id: string | number;
  code: string;
  name: string;
  enabled: boolean;
  priority: number;
  requires_token: boolean;
  auth_status?: string;
  capabilities?: DataSourceCapability | null;
  adapter_class?: string | null;
  provider_metadata?: DataSourceProviderMetadata | null;
  config_json?: {
    capabilities?: DataSourceCapability;
    auth_status?: string;
    last_health_message?: string;
    last_smoke_test?: DataSourceSmokeSummary;
    smoke_test_history?: DataSourceSmokeSummary[];
    adapter_class?: string;
    provider_metadata?: DataSourceProviderMetadata;
    [key: string]: unknown;
  };
  health_status: string;
  last_checked_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DataSourceUpdate = {
  enabled?: boolean;
  priority?: number;
};

export type DataSourceHealthResult = {
  source: DataSource;
  healthy: boolean;
  status: string;
  message: string;
};

export type DataSourceSmokeResult = DataSourceHealthResult & {
  capability: string;
  raw_records: number;
  normalized_records: number;
  validation_errors: string[];
  sample: Array<Record<string, unknown>>;
};
