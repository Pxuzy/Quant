import { apiRequest } from '../../shared/api/client';
import { normalizeNewsResponse } from './news';

export const marketQueryKeys = {
  all: ['market'] as const,
  quotes: (codes: string[]) => [...marketQueryKeys.all, 'quotes', ...codes] as const,
  index: () => [...marketQueryKeys.all, 'index'] as const,
  kline: (code: string, period: string, count: number) => [...marketQueryKeys.all, 'kline', code, period, count] as const,
  news: (keyword: string) => [...marketQueryKeys.all, 'news', keyword] as const,
  search: (keyword: string) => [...marketQueryKeys.all, 'search', keyword] as const,
};

export interface Quote {
  code: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  amount: number;
  pe: number;
  pb: number;
  turnover: number;
  bid1_price: number;
  bid1_vol: number;
  ask1_price: number;
  ask1_vol: number;
  prev_close: number;
  sectors?: string[];
}

export interface KLine {
  date: string;
  open: number;
  high: number;
  close: number;
  low: number;
  volume: number;
}

export interface NewsItem {
  title: string;
  url: string;
  summary: string;
  source: string;
  created_at: string;
  category?: string;
}

export interface SectorRanking {
  name: string;
  category: '行业板块' | '概念板块' | '指数板块';
  change_pct: number;
  up_count: number;
  down_count: number;
  stock_count: number;
  amount: number;
  volume: number;
  leader?: Quote | null;
  fund_flow?: string | null;
  turnover_rate?: number | null;
}

export type SortField = 'change_pct' | 'amount' | 'volume' | 'up_count' | 'down_count';

type NewsResponse = NewsItem[] | { items?: NewsItem[]; data?: NewsItem[]; results?: NewsItem[] };

export function fetchQuotes(codes: string[], signal?: AbortSignal): Promise<Quote[]> {
  return apiRequest<Quote[]>(`/api/market/quote?codes=${codes.join(',')}`, undefined, { signal });
}

export function fetchQuote(code: string, signal?: AbortSignal): Promise<Quote> {
  return apiRequest<Quote>(`/api/market/quote?codes=${code}`, undefined, { signal });
}

export function fetchIndexQuotes(signal?: AbortSignal): Promise<Quote[]> {
  return apiRequest<Quote[]>('/api/market/index', undefined, { signal });
}

export function fetchKline(
  code: string,
  period: string = 'day',
  count: number = 100,
  signal?: AbortSignal,
): Promise<KLine[]> {
  return apiRequest<KLine[]>('/api/market/kline', { code, period, count }, { signal });
}

export function fetchNews(keyword: string = 'A股', limit: number = 10, signal?: AbortSignal, page: number = 1): Promise<NewsItem[]> {
  return apiRequest<NewsResponse>(`/api/market/news?keyword=${encodeURIComponent(keyword)}&limit=${limit}&page=${page}`, undefined, { signal })
    .then(normalizeNewsResponse);
}

export function searchStocks(keyword: string, signal?: AbortSignal): Promise<Array<{code: string; name: string; market: string}>> {
  return apiRequest(`/api/market/search?keyword=${encodeURIComponent(keyword)}`, undefined, { signal });
}

export function fetchSectorRankings(categories: SectorRanking['category'][], signal?: AbortSignal): Promise<SectorRanking[]> {
  const params = new URLSearchParams({ categories: categories.join(',') });
  return apiRequest<SectorRanking[]>(`/api/market/sectors?${params.toString()}`, undefined, { signal });
}
