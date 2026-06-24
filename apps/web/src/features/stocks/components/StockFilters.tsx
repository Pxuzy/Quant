import { useEffect, useRef } from 'react';
import { ReloadOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons';
import { Button, Form, Input, Select, Space } from 'antd';
import { aShareMarketOptions } from '../../../shared/domain/labels';
import { pulseFeedback, useGSAP } from '../../../shared/motion/gsapMotion';
import type { StockFilterValues } from '../types';

type StockFiltersProps = {
  value: StockFilterValues;
  syncing: boolean;
  loading: boolean;
  sourceOptions: { label: string; value: string; disabled?: boolean }[];
  onChange: (next: StockFilterValues) => void;
  onRefresh: () => void;
  onSync: () => void;
};

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '上市', value: 'LISTED' },
  { label: '停牌', value: 'SUSPENDED' },
  { label: '退市', value: 'DELISTED' },
];

const exchangeOptions = [
  { label: '全部交易所', value: '' },
  { label: '上交所', value: 'SSE' },
  { label: '深交所', value: 'SZSE' },
  { label: '北交所', value: 'BSE' },
];

const dailyCoverageOptions = [
  { label: '全部数据日', value: '' },
  { label: '已有日线', value: 'has_data' },
  { label: '需补日线', value: 'needs_repair' },
  { label: '暂无日线', value: 'missing' },
  { label: '完整日线', value: 'complete' },
];

export function StockFilters({
  value,
  syncing,
  loading,
  sourceOptions,
  onChange,
  onRefresh,
  onSync,
}: StockFiltersProps) {
  const [form] = Form.useForm<StockFilterValues>();
  const syncButtonRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    form.setFieldsValue(value);
  }, [form, value]);

  useGSAP(
    () => {
      if (syncButtonRef.current) {
        pulseFeedback(syncButtonRef.current);
      }
    },
    {
      dependencies: [syncing],
      scope: syncButtonRef,
      revertOnUpdate: true,
    },
  );

  return (
    <Form
      form={form}
      className="stock-filters"
      layout="inline"
      initialValues={value}
      onFinish={(values) => {
        onChange({
          keyword: values.keyword?.trim(),
          industry: values.industry?.trim(),
          exchange: values.exchange,
          market: values.market,
          status: values.status,
          dailyCoverage: values.dailyCoverage,
          syncSource: values.syncSource,
        });
      }}
    >
      <Form.Item name="keyword" className="filter-keyword">
        <Input allowClear prefix={<SearchOutlined />} placeholder="代码 / 名称" />
      </Form.Item>

      <Form.Item name="industry" className="filter-industry">
        <Input allowClear placeholder="行业 / 板块" />
      </Form.Item>

      <Form.Item name="exchange">
        <Select className="filter-select" options={exchangeOptions} />
      </Form.Item>

      <Form.Item name="market">
        <Select className="filter-select" options={aShareMarketOptions} />
      </Form.Item>

      <Form.Item name="status">
        <Select className="filter-select" options={statusOptions} />
      </Form.Item>

      <Form.Item name="dailyCoverage">
        <Select className="filter-select-wide" options={dailyCoverageOptions} />
      </Form.Item>

      <Form.Item name="syncSource">
        <Select className="filter-source-select" options={sourceOptions} />
      </Form.Item>

      <Form.Item className="filter-actions">
        <Space wrap>
          <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
            查询
          </Button>
          <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
            刷新
          </Button>
          <span ref={syncButtonRef} className="sync-action-motion">
            <Button icon={<SyncOutlined spin={syncing} />} onClick={onSync} loading={syncing}>
              同步股票池
            </Button>
          </span>
        </Space>
      </Form.Item>
    </Form>
  );
}
