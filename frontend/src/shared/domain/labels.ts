export const marketLabels: Record<string, string> = {
  A_SHARE: '中国 A 股',
  HK: '港股',
  US: '美股',
};

export const exchangeLabels: Record<string, string> = {
  SSE: '上交所',
  SH: '上交所',
  XSHG: '上交所',
  SZSE: '深交所',
  SZ: '深交所',
  XSHE: '深交所',
  BSE: '北交所',
  BJ: '北交所',
  HKEX: '港交所',
  NYSE: '纽约证券交易所',
  NASDAQ: '纳斯达克',
};

export const adjustTypeLabels: Record<string, string> = {
  none: '不复权',
  qfq: '前复权',
  hfq: '后复权',
  forward: '前复权',
  backward: '后复权',
};

export const capabilityLabels: Record<string, string> = {
  stock_list: '股票池',
  daily_bars: '日线行情',
  calendars: '交易日历',
  trading_calendars: '交易日历',
  none: '无可取样能力',
};

export const taskTypeLabels: Record<string, string> = {
  stock_list: '股票池',
  daily_bars: '日线行情',
  daily_bars_market_repair: '市场级日线缺口补齐',
  calendars: '交易日历',
  sync: '同步记录',
};

export const sourceModeLabels: Record<string, string> = {
  auto: '自动选择（按优先级）',
};

export const providerTypeLabels: Record<string, string> = {
  python_package: 'Python 包',
  node_package: 'Node 包',
  external_api: '外部 API',
};

export const stabilityLabels: Record<string, string> = {
  best_effort: '尽力可用',
  community: '社区维护',
  official: '官方',
};

export const authModeLabels: Record<string, string> = {
  none: '免凭证',
  token: 'Token 凭证',
};

export const authStatusLabels: Record<string, string> = {
  not_required: '不需要凭证',
  configured: 'Token 已配置',
  missing: 'Token 未配置',
  unknown: '状态未知',
};

export const layerLabels: Record<string, string> = {
  raw: '原始层',
  bronze: '铜层',
  silver: '银层',
  gold: '金层',
};

export const storageTypeLabels: Record<string, string> = {
  postgres: '元数据库',
  sqlite: 'SQLite 本地备用',
  parquet: 'Parquet 数据湖',
  duckdb: 'DuckDB 查询引擎',
};

export const qualityCheckTypeLabels: Record<string, string> = {
  basic: '基础检查',
  duplicate_record: '重复记录',
  field_completeness: '字段完整率',
  freshness: '数据时效',
  missing_trade_date: '缺失交易日',
  missing_trade_date_by_symbol: '单股缺失交易日',
  negative_price: '价格负值',
  negative_turnover: '成交量/额负值',
  ohlc_high_bound: '最高价边界',
  ohlc_low_bound: '最低价边界',
  ohlc_range: 'OHLC 区间',
  row_count: '记录数',
  stock_pool_missing_daily_bars: '股票池日线覆盖',
  storage_availability: '存储可读性',
};

export const logLevelLabels: Record<string, string> = {
  debug: '调试',
  info: '信息',
  warning: '警告',
  error: '错误',
};

export const booleanLabels = {
  enabled: '已启用',
  disabled: '已禁用',
  yes: '是',
  no: '否',
  open: '开市',
  closed: '休市',
};

function formatByMap(value: unknown, labels: Record<string, string>, fallback = '-') {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }

  const key = String(value);
  return labels[key] ?? key;
}

export function formatMarket(value: unknown, fallback = '-') {
  return formatByMap(value, marketLabels, fallback);
}

export function formatExchange(value: unknown, fallback = '-') {
  return formatByMap(value, exchangeLabels, fallback);
}

export function formatAdjustType(value: unknown, fallback = '-') {
  return formatByMap(value || 'none', adjustTypeLabels, fallback);
}

export function formatCapability(value: unknown, fallback = '-') {
  return formatByMap(value, capabilityLabels, fallback);
}

export function formatTaskType(value: unknown, fallback = '-') {
  return formatByMap(value, taskTypeLabels, fallback);
}

export function formatSourceMode(value: unknown, fallback = '-') {
  return formatByMap(value, sourceModeLabels, fallback);
}

export function formatProviderType(value: unknown, fallback = '-') {
  return formatByMap(value, providerTypeLabels, fallback);
}

export function formatAuthMode(value: unknown, fallback = '-') {
  return formatByMap(value, authModeLabels, fallback);
}

export function formatAuthStatus(value: unknown, fallback = '-') {
  return formatByMap(value, authStatusLabels, fallback);
}

export function formatStability(value: unknown, fallback = '-') {
  return formatByMap(value, stabilityLabels, fallback);
}

export function formatLayer(value: unknown, fallback = '-') {
  return formatByMap(value, layerLabels, fallback);
}

export function formatStorageType(value: unknown, fallback = '-') {
  return formatByMap(value, storageTypeLabels, fallback);
}

export function formatQualityCheckType(value: unknown, fallback = '-') {
  return formatByMap(value, qualityCheckTypeLabels, fallback);
}

export function formatLogLevel(value: unknown, fallback = '-') {
  return formatByMap(value, logLevelLabels, fallback);
}

export const marketOptions = [
  { label: '全部市场', value: '' },
  { label: marketLabels.A_SHARE, value: 'A_SHARE' },
  { label: marketLabels.HK, value: 'HK' },
  { label: marketLabels.US, value: 'US' },
];

export const aShareMarketOptions = [{ label: marketLabels.A_SHARE, value: 'A_SHARE' }];

export const sourceModeOptions = [{ label: sourceModeLabels.auto, value: 'auto' }];
