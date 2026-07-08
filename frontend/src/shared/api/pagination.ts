export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
};

export type LoosePage<T> = {
  items?: T[];
  data?: T[] | { items?: T[]; list?: T[]; total?: number; page?: number; page_size?: number };
  list?: T[];
  records?: T[];
  total?: number;
  count?: number;
  page?: number;
  current?: number;
  page_size?: number;
  pageSize?: number;
  per_page?: number;
};

export function normalizePageResult<T>(
  payload: LoosePage<T>,
  fallbackPage: number,
  fallbackPageSize: number,
): PageResult<T> {
  const nested = Array.isArray(payload.data) ? undefined : payload.data;
  const items =
    payload.items ??
    payload.list ??
    payload.records ??
    (Array.isArray(payload.data) ? payload.data : undefined) ??
    nested?.items ??
    nested?.list ??
    [];
  const total = payload.total ?? payload.count ?? nested?.total ?? items.length;
  const page = payload.page ?? payload.current ?? nested?.page ?? fallbackPage;
  const pageSize =
    payload.pageSize ??
    payload.page_size ??
    payload.per_page ??
    nested?.page_size ??
    fallbackPageSize;

  return { items, total, page, pageSize };
}
