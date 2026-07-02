import { CalendarOutlined, FileTextOutlined, SyncOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, DatePicker, Descriptions, Empty, Form, Input, InputNumber, Row, Segmented, Select, Space, Statistic, Table, Tabs, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { type Dayjs } from 'dayjs';
import type { FormInstance } from 'antd';
import type { RefObject } from 'react';

import type { DailyBarsMarketRepairPreviewItem, DailyBarsMarketRepairPreviewResponse } from '../../../../features/market-data/types';
import { formatDate, formatNumber } from '../../../../shared/components/formatters';
import { formatMarket } from '../../../../shared/domain/labels';

const DEFAULT_MARKET = 'A_SHARE';
const SYMBOL_EXAMPLE = '600519';
const DEFAULT_DATE_RANGE: [Dayjs, Dayjs] = [dayjs().subtract(90, 'day'), dayjs()];
const DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20;
const MAX_MARKET_REPAIR_SYMBOLS = 200;
const DEFAULT_MARKET_REPAIR_START_POLICY = 'requested_start';
const DEFAULT_ADJUST_TYPE: 'none' | 'qfq' | 'hfq' = 'none';
const adjustTypeOptions = [
  { label: '不复权', value: 'none' },
  { label: '前复权', value: 'qfq' },
  { label: '后复权', value: 'hfq' },
];

type DailyBarsMode = 'single' | 'market-repair';

type MarketRepairFormValues = {
  source?: string;
  market?: string;
  dateRange?: [Dayjs, Dayjs];
  maxSymbols?: number;
  startPolicy?: 'requested_start' | 'listing_date';
  adjustType?: 'none' | 'qfq' | 'hfq';
};

function buildMarketRepairPreviewColumns(): ColumnsType<DailyBarsMarketRepairPreviewItem> {
  return [
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 92,
      render: (value: string, record: { name?: string | null }) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary">{record.name || '-'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '交易所',
      dataIndex: 'exchange',
      width: 82,
      render: (value: string) => value || '-',
    },
    {
      title: '补齐范围',
      key: 'range',
      width: 160,
      render: (_: unknown, record: { start_date?: string | null; end_date?: string | null }) => `${formatDate(record.start_date)} ~ ${formatDate(record.end_date)}`,
    },
    {
      title: '缺口',
      dataIndex: 'missing_trade_days',
      width: 72,
      align: 'right',
      render: (value: number) => formatNumber(value),
    },
  ];
}

function formatMarketRepairStartPolicy(value?: string | null) {
  return value === 'listing_date' ? '从上市日起' : '按填写起始日';
}

function MarketRepairPreviewPanel({
  preview,
  loading,
  error,
}: {
  preview?: DailyBarsMarketRepairPreviewResponse;
  loading: boolean;
  error?: unknown;
}) {
  const sampleItems = preview?.sample_items ?? [];
  const columns = buildMarketRepairPreviewColumns();
  const candidateSources = preview?.candidate_sources ?? [];
  const supportedExchanges = preview?.supported_exchanges ?? [];

  if (loading) {
    return (
      <div className="market-repair-preview-panel">
        <Alert type="info" showIcon message="正在生成补齐计划预览" description="系统会检查股票池、开市日和现有日线缺口。" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-repair-preview-panel">
        <Alert
          type="error"
          showIcon
          message="补齐计划预览失败"
          description={error instanceof Error ? error.message : '预览接口暂不可用，请稍后重试或直接创建任务。'}
        />
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="market-repair-preview-panel market-repair-preview-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未预览补齐计划" />
      </div>
    );
  }

  return (
    <div className="market-repair-preview-panel">
      <div className="market-repair-preview-heading">
        <Typography.Text strong>补齐计划预览</Typography.Text>
        <Space size={[6, 6]} wrap>
          <Tag color="blue">{formatMarket(preview.market, '全部市场')}</Tag>
          {preview.selected_source ? <Tag color="green">实际来源 {preview.selected_source}</Tag> : null}
        </Space>
      </div>
      {preview.message ? <Alert type="success" showIcon message={preview.message} /> : null}
      <div className="market-repair-preview-stats">
        <Statistic title="计划股票" value={preview.planned_symbols ?? 0} suffix="只" />
        <Statistic title="预计缺口" value={preview.planned_missing_symbol_days ?? 0} suffix="日" />
        <Statistic title="开市日" value={preview.open_dates_count ?? 0} suffix="天" />
        <Statistic title="安全上限" value={preview.max_symbols ?? 0} suffix="只" />
      </div>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="日期范围">
          {formatDate(preview.start_date)} ~ {formatDate(preview.end_date)}
        </Descriptions.Item>
        <Descriptions.Item label="补齐起点">{formatMarketRepairStartPolicy(preview.start_policy)}</Descriptions.Item>
        <Descriptions.Item label="股票池">{formatNumber(preview.stock_pool_count)} 只</Descriptions.Item>
        <Descriptions.Item label="预览来源">{preview.source || '-'} / {preview.selected_source || '-'}</Descriptions.Item>
        <Descriptions.Item label="候选来源">
          {candidateSources.length ? (
            <Space size={[6, 6]} wrap>
              {candidateSources.map((source) => (
                <Tag key={source}>{source}</Tag>
              ))}
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="支持交易所">
          {supportedExchanges.length ? (
            <Space size={[6, 6]} wrap>
              {supportedExchanges.map((exchange) => (
                <Tag color="geekblue" key={exchange}>
                  {exchange}
                </Tag>
              ))}
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
      </Descriptions>
      <Table
        rowKey={(record) => `${record.symbol}-${record.exchange ?? ''}-${record.start_date ?? ''}-${record.end_date ?? ''}`}
        columns={columns}
        dataSource={sampleItems}
        pagination={false}
        size="small"
        scroll={{ x: 420 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无样例股票" /> }}
      />
    </div>
  );
}

type SyncOperationTabsProps = {
  searchFocus?: string;
  activeTab: DailyBarsMode | 'stock-list' | 'calendars' | 'daily-bars';
  onTabChange: (tab: DailyBarsMode | 'stock-list' | 'calendars' | 'daily-bars') => void;
  dailyBarsMode: DailyBarsMode;
  onDailyBarsModeChange: (mode: DailyBarsMode) => void;
  onResetMarketRepairPreview: () => void;
  stockCardRef: RefObject<HTMLDivElement>;
  dailyBarsCardRef: RefObject<HTMLDivElement>;
  calendarCardRef: RefObject<HTMLDivElement>;
  stockForm: FormInstance<{ source?: string; market?: string }>;
  dailyBarsForm: FormInstance<{
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
    adjustType?: 'none' | 'qfq' | 'hfq';
  }>;
  marketRepairForm: FormInstance<MarketRepairFormValues>;
  calendarForm: FormInstance<{ source?: string; market?: string; dateRange?: [Dayjs, Dayjs] }>;
  stockSourceOptions: Array<{ label: string; value: string }>;
  dailyBarsSourceOptions: Array<{ label: string; value: string }>;
  calendarSourceOptions: Array<{ label: string; value: string }>;
  dataSourcesLoading: boolean;
  previewDailyBarsMarketRepairData?: DailyBarsMarketRepairPreviewResponse;
  previewDailyBarsMarketRepairLoading: boolean;
  previewDailyBarsMarketRepairError?: unknown;
  isCreatingTask: boolean;
  onStockSync: (values: { source?: string; market?: string }) => void;
  onDailyBarsSync: (values: {
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
    adjustType?: 'none' | 'qfq' | 'hfq';
  }) => void;
  onMarketDailyBarsRepair: (values: MarketRepairFormValues) => void;
  onMarketDailyBarsRepairPreview: () => void;
  onCalendarSync: (values: { source?: string; market?: string; dateRange?: [Dayjs, Dayjs] }) => void;
};

export function SyncOperationTabs({
  searchFocus,
  activeTab,
  onTabChange,
  dailyBarsMode,
  onDailyBarsModeChange,
  onResetMarketRepairPreview,
  stockCardRef,
  dailyBarsCardRef,
  calendarCardRef,
  stockForm,
  dailyBarsForm,
  marketRepairForm,
  calendarForm,
  stockSourceOptions,
  dailyBarsSourceOptions,
  calendarSourceOptions,
  dataSourcesLoading,
  previewDailyBarsMarketRepairData,
  previewDailyBarsMarketRepairLoading,
  previewDailyBarsMarketRepairError,
  isCreatingTask,
  onStockSync,
  onDailyBarsSync,
  onMarketDailyBarsRepair,
  onMarketDailyBarsRepairPreview,
  onCalendarSync,
}: SyncOperationTabsProps) {
  const marketRepairDateRange = Form.useWatch('dateRange', marketRepairForm);
  const [startDate, endDate] = marketRepairDateRange ?? [];
  const marketRepairDateRangeLabel =
    startDate?.isValid() && endDate?.isValid()
      ? `${formatDate(startDate.format('YYYY-MM-DD'))} ~ ${formatDate(endDate.format('YYYY-MM-DD'))}`
      : undefined;

  const stockListPane = (
    <div className={`sync-operation-pane${searchFocus === 'stock-list' ? ' is-focused' : ''}`} ref={stockCardRef}>
      <div className="sync-operation-intro">
        <Space size={8}>
          <SyncOutlined />
          <Typography.Title level={5}>股票池</Typography.Title>
        </Space>
        <Typography.Text type="secondary">从启用来源更新 A 股基础列表，作为日线补齐和交易日历校验的入口数据。</Typography.Text>
      </div>
      <Form className="sync-operation-form" form={stockForm} layout="vertical" initialValues={{ source: 'auto', market: DEFAULT_MARKET }} onFinish={onStockSync}>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item label="数据源" name="source">
              <Select options={stockSourceOptions} loading={dataSourcesLoading} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="市场" name="market">
              <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={isCreatingTask}>
          更新股票池
        </Button>
      </Form>
    </div>
  );

  const dailyBarsPane = (
    <div
      className={`sync-operation-pane sync-operation-pane-primary${
        searchFocus === 'daily-bars' || searchFocus === 'daily-bars-market-repair' ? ' is-focused' : ''
      }`}
      ref={dailyBarsCardRef}
    >
      <div className="sync-operation-intro">
        <Space size={8}>
          <FileTextOutlined />
          <Typography.Title level={5}>日线同步</Typography.Title>
        </Space>
        <Typography.Text type="secondary">
          {dailyBarsMode === 'single'
            ? '指定单只股票和日期范围，写入标准日线行情与整合批次。'
            : '按市场和日期范围创建受控补齐任务，由后端逐只修复股票-交易日缺口。'}
        </Typography.Text>
      </div>
      <Segmented
        className="sync-operation-mode"
        block
        value={dailyBarsMode}
        onChange={(value) => {
          onDailyBarsModeChange(value as DailyBarsMode);
          if (value !== 'market-repair') {
            onResetMarketRepairPreview();
          }
        }}
        options={[
          { label: '单股日线', value: 'single' },
          { label: '市场缺口补齐', value: 'market-repair' },
        ]}
      />
      {dailyBarsMode === 'single' ? (
        <Form
          className="sync-operation-form"
          form={dailyBarsForm}
          layout="vertical"
          initialValues={{
            source: 'auto',
            market: DEFAULT_MARKET,
            symbol: '',
            dateRange: DEFAULT_DATE_RANGE,
            adjustType: DEFAULT_ADJUST_TYPE,
          }}
          onFinish={onDailyBarsSync}
        >
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="股票代码" name="symbol" rules={[{ required: true, message: '请输入股票代码' }]}>
                <Input placeholder={`例如 ${SYMBOL_EXAMPLE}`} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="市场" name="market">
                <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker className="full-width-control" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="数据源" name="source">
                <Select options={dailyBarsSourceOptions} loading={dataSourcesLoading} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="复权口径" name="adjustType">
            <Segmented block options={adjustTypeOptions} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={isCreatingTask}>
            同步单股日线
          </Button>
        </Form>
      ) : (
        <Form
          className="sync-operation-form"
          form={marketRepairForm}
          layout="vertical"
          initialValues={{
            source: 'auto',
            market: DEFAULT_MARKET,
            dateRange: DEFAULT_DATE_RANGE,
            maxSymbols: DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
            startPolicy: DEFAULT_MARKET_REPAIR_START_POLICY,
            adjustType: DEFAULT_ADJUST_TYPE,
          }}
          onFinish={onMarketDailyBarsRepair}
          onValuesChange={() => onResetMarketRepairPreview()}
        >
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="市场" name="market">
                <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label="最大股票数"
                name="maxSymbols"
                rules={[{ required: true, message: '请设置本次最多处理的股票数' }]}
              >
                <InputNumber className="full-width-control" min={1} max={MAX_MARKET_REPAIR_SYMBOLS} precision={0} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="数据源" name="source">
                <Select options={dailyBarsSourceOptions} loading={dataSourcesLoading} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker className="full-width-control" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="补齐起点" name="startPolicy">
                <Segmented
                  block
                  options={[
                    { label: '按填写起始日', value: 'requested_start' },
                    { label: '从上市日', value: 'listing_date' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="复权口径" name="adjustType">
            <Segmented block options={adjustTypeOptions} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="市场级补齐不填写股票代码，建议先预览股票池、开市日和缺口计划，再创建任务。"
            description={
              marketRepairDateRangeLabel
                ? `当前补齐范围 ${marketRepairDateRangeLabel}；选择“从上市日”时，每只股票会从上市日与填写起始日中较晚的一天开始补齐。`
                : undefined
            }
          />
          <MarketRepairPreviewPanel
            preview={previewDailyBarsMarketRepairData}
            loading={previewDailyBarsMarketRepairLoading}
            error={previewDailyBarsMarketRepairError}
          />
          <Space className="market-repair-actions">
            <Button loading={previewDailyBarsMarketRepairLoading} onClick={onMarketDailyBarsRepairPreview}>
              预览补齐计划
            </Button>
            <Button type="primary" htmlType="submit" loading={isCreatingTask}>
              创建市场补齐任务
            </Button>
          </Space>
        </Form>
      )}
    </div>
  );

  const calendarPane = (
    <div className={`sync-operation-pane${searchFocus === 'calendars' ? ' is-focused' : ''}`} ref={calendarCardRef}>
      <div className="sync-operation-intro">
        <Space size={8}>
          <CalendarOutlined />
          <Typography.Title level={5}>交易日历</Typography.Title>
        </Space>
        <Typography.Text type="secondary">补齐交易日历覆盖，供日线缺口检查和后续调度判断使用。</Typography.Text>
      </div>
      <Form
        className="sync-operation-form"
        form={calendarForm}
        layout="vertical"
        initialValues={{ source: 'auto', market: DEFAULT_MARKET, dateRange: DEFAULT_DATE_RANGE }}
        onFinish={onCalendarSync}
      >
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item label="市场" name="market">
              <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
              <DatePicker.RangePicker className="full-width-control" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="数据源" name="source">
              <Select options={calendarSourceOptions} loading={dataSourcesLoading} />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={isCreatingTask}>
          同步交易日历
        </Button>
      </Form>
    </div>
  );

  const syncOperationItems = [
    { key: 'daily-bars', label: '日线补齐', children: dailyBarsPane },
    { key: 'stock-list', label: '股票池', children: stockListPane },
    { key: 'calendars', label: '交易日历', children: calendarPane },
  ];

  return (
    <Card className="sync-operations-card stock-detail-panel" title="创建同步任务">
      <Tabs activeKey={activeTab} onChange={(key) => onTabChange(key as DailyBarsMode | 'stock-list' | 'calendars' | 'daily-bars')} items={syncOperationItems} />
    </Card>
  );
}
