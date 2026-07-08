// Extracted from StockDetailPage — column definitions
import type { ColumnsType } from 'antd/es/table';
import { Typography } from 'antd';
import type { DailyBar } from '../../../../features/market-data/types';
import { formatDate, formatDateTime, formatDecimal, formatNumber } from '../../../../shared/components/formatters';
import { formatAdjustType } from '../../../../shared/domain/labels';


export function buildDailyColumns(): ColumnsType<DailyBar> {
  return [
    { title: '交易日', dataIndex: 'trade_date', width: 120, render: (value) => formatDate(value) },
    { title: '开盘', dataIndex: 'open', width: 100, render: (value) => formatDecimal(value) },
    { title: '最高', dataIndex: 'high', width: 100, render: (value) => formatDecimal(value) },
    { title: '最低', dataIndex: 'low', width: 100, render: (value) => formatDecimal(value) },
    {
      title: '收盘',
      dataIndex: 'close',
      width: 100,
      render: (value) => <Typography.Text strong>{formatDecimal(value)}</Typography.Text>,
    },
    { title: '成交量', dataIndex: 'volume', width: 130, render: (value) => formatNumber(value) },
    { title: '成交额', dataIndex: 'amount', width: 140, render: (value) => formatNumber(value) },
    { title: '复权口径', dataIndex: 'adjust_type', width: 110, render: (value) => formatAdjustType(value) },
    { title: '来源', dataIndex: 'source', width: 120 },
    { title: '更新时间', dataIndex: 'ingested_at', width: 180, render: (value) => formatDateTime(value) },
  ];
}
