export type DailyBar = {
  symbol: string;
  exchange: string;
  market: string;
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  pre_close?: number | null;
  volume: number;
  amount: number;
  adjust_factor?: number | null;
  adjust_type: string;
  source: string;
  ingested_at: string;
};

export type DailyBarsListParams = {
  symbol?: string;
  market?: string;
  startDate?: string;
  endDate?: string;
  sortOrder?: 'asc' | 'desc';
  page: number;
  pageSize: number;
};

export type DailyBarsSyncRequest = {
  source?: string;
  market?: string;
  symbol: string;
  start_date: string;
  end_date: string;
};

export type DailyBarsMarketRepairRequest = {
  source?: string;
  market?: string;
  start_date: string;
  end_date: string;
  max_symbols?: number;
};

export type DailyBarsMarketRepairPreviewItem = {
  symbol: string;
  exchange?: string | null;
  name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  missing_trade_days?: number | null;
};

export type DailyBarsMarketRepairPreviewResponse = {
  source?: string | null;
  selected_source?: string | null;
  candidate_sources?: string[];
  market?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  max_symbols?: number | null;
  stock_pool_count?: number | null;
  open_dates_count?: number | null;
  planned_symbols?: number | null;
  planned_missing_symbol_days?: number | null;
  supported_exchanges?: string[];
  sample_items?: DailyBarsMarketRepairPreviewItem[];
  message?: string | null;
};
