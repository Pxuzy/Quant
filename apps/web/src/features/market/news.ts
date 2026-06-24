export type NewsResponse<T> = T[] | { items?: T[]; data?: T[]; results?: T[] };

export function normalizeNewsResponse<T>(payload: NewsResponse<T>): T[] {
  if (Array.isArray(payload)) return payload;
  return payload.items ?? payload.data ?? payload.results ?? [];
}
