import { useMemo, useRef } from 'react';
import type { ProColumns } from '@ant-design/pro-components';
import { ProTable } from '@ant-design/pro-components';
import { Button, Empty, Progress, Space, Typography } from 'antd';
import { formatDate, formatDateTime, formatPercent } from '../../../shared/components/formatters';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatExchange, formatMarket } from '../../../shared/domain/labels';
import type { PageResult } from '../../../shared/api/pagination';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';
import type { Stock, StockListParams } from '../types';

type StocksTableProps = {
  data?: PageResult<Stock>;
  params: StockListParams;
  loading: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onViewDetails: (stock: Stock) => void;
};

function buildColumns(onViewDetails: (stock: Stock) => void): ProColumns<Stock>[] {
  return [
  {
    title: '代码',
    dataIndex: 'symbol',
    width: 120,
    fixed: 'left',
    render: (_, record) => <Typography.Text strong>{record.symbol}</Typography.Text>,
  },
  {
    title: '名称',
    dataIndex: 'name',
    width: 160,
    render: (_, record) => record.name || '-',
  },
  {
    title: '市场',
    dataIndex: 'market',
    width: 96,
    renderText: (value) => formatMarket(value),
  },
  {
    title: '交易所',
    dataIndex: 'exchange',
    width: 96,
    renderText: (value) => formatExchange(value),
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 96,
    render: (_, record) => <StatusTag value={record.status} />,
  },
  {
    title: '行业',
    dataIndex: 'industry',
    ellipsis: true,
    renderText: (value) => value || '-',
  },
  {
    title: '上市日期',
    dataIndex: 'listing_date',
    width: 120,
    render: (_, record) => formatDate(record.listing_date ?? record.listingDate),
  },
  {
    title: '最新数据日',
    dataIndex: 'latest_data_date',
    width: 130,
    render: (_, record) => formatDate(record.latest_data_date ?? record.latestDataDate),
  },
  {
    title: '数据完整度',
    dataIndex: 'data_completeness',
    width: 150,
    render: (_, record) => {
      const value = record.data_completeness ?? record.dataCompleteness;
      if (value === undefined || value === null) {
        return <Typography.Text type="secondary">暂无日线</Typography.Text>;
      }
      const percent = Math.round(value * 100);
      return (
        <Space direction="vertical" size={0} className="stock-completeness">
          <Progress percent={percent} size="small" status={percent >= 95 ? 'success' : 'normal'} />
          <Typography.Text type="secondary">{formatPercent(value * 100)}</Typography.Text>
        </Space>
      );
    },
  },
  {
    title: '来源',
    dataIndex: 'source',
    width: 112,
    renderText: (value) => value || '-',
  },
  {
    title: '更新时间',
    dataIndex: 'updated_at',
    width: 180,
    render: (_, record) => formatDateTime(record.updated_at ?? record.updatedAt),
  },
  {
    title: '操作',
    valueType: 'option',
    width: 88,
    fixed: 'right',
    render: (_, record) => (
      <Button type="link" size="small" onClick={() => onViewDetails(record)}>
        详情
      </Button>
    ),
  },
  ];
}

export function StocksTable({ data, params, loading, onPageChange, onViewDetails }: StocksTableProps) {
  const items = data?.items ?? [];
  const tableRef = useRef<HTMLDivElement>(null);
  const columns = useMemo(() => buildColumns(onViewDetails), [onViewDetails]);
  const rowsMotionKey = items.map((item) => item.id ?? item.symbol).join('|');

  useGSAP(
    () => {
      const root = tableRef.current;
      if (!root || loading) {
        return;
      }

      const rows = root.querySelectorAll('.ant-table-tbody > tr:not(.ant-table-placeholder)');
      if (rows.length > 0) {
        fadeInUp(rows, { duration: 0.22, stagger: 0.018, y: 5 });
      }
    },
    {
      dependencies: [loading, rowsMotionKey],
      scope: tableRef,
      revertOnUpdate: true,
    },
  );

  return (
    <div ref={tableRef}>
      <ProTable<Stock>
        className="stocks-table"
        rowKey={(record) => String(record.id ?? record.symbol)}
        columns={columns}
        dataSource={items}
        loading={loading}
        search={false}
        options={false}
        cardBordered={false}
        tableAlertRender={false}
        toolBarRender={false}
        scroll={{ x: 1328 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无股票记录，或当前筛选条件没有匹配结果。"
            />
          ),
        }}
        pagination={{
          current: params.page,
          pageSize: params.pageSize,
          total: data?.total ?? 0,
          showSizeChanger: false,
          showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${total} 条`,
          onChange: onPageChange,
        }}
      />
    </div>
  );
}
