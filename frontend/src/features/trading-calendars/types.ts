export type TradingCalendarDay = {
  id: number;
  market: string;
  trade_date: string;
  is_open: boolean;
  source: string;
  updated_at: string;
};

export type TradingCalendarListParams = {
  market?: string;
  startDate?: string;
  endDate?: string;
  openStatus?: string;
  page?: number;
  pageSize?: number;
};

export type TradingCalendarSyncRequest = {
  source: string;
  market: string;
  start_date: string;
  end_date: string;
};
