export class ApiError extends Error {
  readonly status?: number;
  readonly detail?: unknown;

  constructor(message: string, status?: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
};

function buildUrl(path: string, params?: Record<string, string | number | undefined>) {
  const isAbsoluteBaseUrl = /^https?:\/\//i.test(API_BASE_URL);
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);

  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });

  return isAbsoluteBaseUrl ? url.toString() : url.pathname + url.search;
}

async function parseError(response: Response) {
  const contentType = response.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    const payload = await response.json();
    const message =
      payload?.message ?? payload?.detail ?? payload?.error ?? `请求失败 (${response.status})`;
    return new ApiError(String(message), response.status, payload);
  }

  const text = await response.text();
  return new ApiError(text || `请求失败 (${response.status})`, response.status);
}

export async function apiRequest<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    method: options.method ?? 'GET',
    signal: options.signal,
    headers: {
      Accept: 'application/json',
      ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
