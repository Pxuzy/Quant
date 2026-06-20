import dayjs from 'dayjs';

export function formatDate(value?: string | null) {
  if (!value) {
    return '-';
  }

  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : value;
}

export function formatDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }

  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : value;
}

export function formatNumber(value?: number | null) {
  if (value === undefined || value === null) {
    return '-';
  }

  return value.toLocaleString('zh-CN');
}

export function formatDecimal(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '-';
  }

  return value.toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatSignedDecimal(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '-';
  }

  const sign = value > 0 ? '+' : '';
  return `${sign}${formatDecimal(value, digits)}`;
}

export function formatPercent(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '-';
  }

  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatBytes(value?: number | null) {
  if (value === undefined || value === null) {
    return '-';
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  const digits = unitIndex === 0 ? 0 : 2;
  return `${size.toFixed(digits)} ${units[unitIndex]}`;
}
