// ponytail: 每端点单独函数 + 共享 query key，不做泛化 wrapper — 3 个端点不值得

import { apiRequest } from '../../shared/api/client';

export interface WatchlistItem {
  id: number;
  symbol: string;
  note: string | null;
  sort_order: number;
  added_at: string;
}

export const watchlistQueryKeys = {
  all: ['watchlist'] as const,
  list: () => [...watchlistQueryKeys.all, 'list'] as const,
};

export async function fetchWatchlist(signal?: AbortSignal): Promise<WatchlistItem[]> {
  return apiRequest<WatchlistItem[]>('/api/watchlist', undefined, { signal });
}

export async function addWatchlistItem(symbol: string, note?: string): Promise<WatchlistItem> {
  return apiRequest<WatchlistItem>(
    '/api/watchlist/items',
    undefined,
    { method: 'POST', body: { symbol, note } },
  );
}

export async function removeWatchlistItem(symbol: string): Promise<void> {
  await apiRequest<void>(`/api/watchlist/items/${encodeURIComponent(symbol)}`, undefined, {
    method: 'DELETE',
  });
}

export async function reorderWatchlist(symbols: string[]): Promise<{ updated: number }> {
  return apiRequest<{ updated: number }>(
    '/api/watchlist/items/reorder',
    undefined,
    { method: 'PUT', body: { symbols } },
  );
}
