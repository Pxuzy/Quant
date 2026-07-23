import { useMemo, useRef } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { CheckCircleOutlined, DatabaseOutlined, SyncOutlined } from '@ant-design/icons';
import { App as AntApp, Card, Col, Row, Space, Statistic, Typography } from 'antd';
import { StockFilters } from './components/StockFilters';
import { StocksTable } from './components/StocksTable';
import { useStocksQuery, useSyncStocksMutation } from '../../../features/stocks/api';
import type { StockFilterValues, StockListParams } from '../../../features/stocks/types';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import { RecentSyncTasks } from '../sync-tasks/components/RecentSyncTasks';
import { ErrorState } from '../../../shared/components/ErrorState';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

const DEFAULT_PAGE_SIZE = 20;
const V1_MARKET = 'A_SHARE';

function normalizeV1Market(market?: string) {
  return market === V1_MARKET ? market : V1_MARKET;
}

export function StocksWorkbenchPage() {
  const { message } = AntApp.useApp();
  const workbenchRef = useRef<HTMLDivElement>(null);
  const search = useSearch({ from: '/stocks' });
  const navigate = useNavigate({ from: '/stocks' });

  const filters = useMemo<StockFilterValues>(
    () => ({
      keyword: search.keyword ?? '',
      industry: search.industry ?? '',
      exchange: search.exchange ?? '',
      market: normalizeV1Market(search.market),
      status: search.status ?? '',
      dailyCoverage: search.dailyCoverage ?? 'has_data',
      syncSource: search.syncSource ?? 'auto',
    }),
    [
      search.dailyCoverage,
      search.exchange,
      search.industry,
      search.keyword,
      search.market,
      search.status,
      search.syncSource,
    ],
  );

  const pagination = useMemo(
    () => ({
      page: search.page ?? 1,
      pageSize: search.pageSize ?? DEFAULT_PAGE_SIZE,
    }),
    [search.page, search.pageSize],
  );

  const params = useMemo<StockListParams>(
    () => ({
      keyword: filters.keyword?.trim(),
      industry: filters.industry?.trim(),
      exchange: filters.exchange,
      market: filters.market,
      status: filters.status,
      dailyCoverage: filters.dailyCoverage,
      page: pagination.page,
      pageSize: pagination.pageSize,
    }),
    [
      filters.dailyCoverage,
      filters.exchange,
      filters.industry,
      filters.keyword,
      filters.market,
      filters.status,
      pagination.page,
      pagination.pageSize,
    ],
  );

  const stocksQuery = useStocksQuery(params);
  const dataSourcesQuery = useDataSourcesQuery();
  const syncMutation = useSyncStocksMutation();

  const sourceOptions = useMemo(() => {
    const enabledSources = (dataSourcesQuery.data ?? [])
      .filter((source) => source.enabled && source.config_json?.capabilities?.stock_list)
      .map((source) => ({
        label: `${source.name} (${source.code})`,
        value: source.code,
      }));

    return [
      { label: '自动选择（按优先级）', value: 'auto' },
      ...enabledSources,
    ];
  }, [dataSourcesQuery.data]);

  const activeFilters = useMemo(() => {
    return [
      filters.keyword,
      filters.industry,
      filters.exchange,
      filters.status,
      filters.dailyCoverage,
    ].filter(Boolean).length;
  }, [filters.dailyCoverage, filters.exchange, filters.industry, filters.keyword, filters.status]);

  const handleFilterChange = (next: StockFilterValues) => {
    void navigate({
      search: {
        keyword: next.keyword || undefined,
        industry: next.industry || undefined,
        exchange: next.exchange || undefined,
        market: next.market || undefined,
        status: next.status || undefined,
        dailyCoverage: next.dailyCoverage || undefined,
        syncSource: next.syncSource || undefined,
        page: 1,
        pageSize: pagination.pageSize,
      },
    });
  };

  const handleSync = () => {
    syncMutation.mutate(
      { source: filters.syncSource || 'auto', market: filters.market || undefined },
      {
        onSuccess: () => {
          void message.success('已创建同步任务，任务开始执行后会写入股票池');
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '同步任务创建失败');
        },
      },
    );
  };

  useGSAP(
    () => {
      const root = workbenchRef.current;
      if (!root) {
        return;
      }

      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.05, y: 8 });

      const tableCard = root.querySelector('.table-card');
      if (tableCard) {
        fadeInUp(tableCard, { delay: 0.08, y: 8 });
      }

      const tasksPanel = root.querySelector('.tasks-panel');
      if (tasksPanel) {
        fadeInUp(tasksPanel, { delay: 0.12, y: 8 });
      }
    },
    { scope: workbenchRef },
  );

  return (
    <div className="workbench" ref={workbenchRef}>
      <div className="workbench-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>股票池</Typography.Title>
          <Typography.Text type="secondary">数据系统 / 全部 A 股股票、基础资料和后续单股详情入口</Typography.Text>
        </Space>
      </div>

      <Row gutter={[16, 16]} className="summary-row">
        <Col xs={24} sm={12} lg={8}>
          <Card className="motion-summary-card">
            <Statistic
              title="当前结果"
              value={stocksQuery.data?.total ?? 0}
              suffix="只"
              prefix={<DatabaseOutlined />}
              loading={stocksQuery.isLoading}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card className="motion-summary-card">
            <Statistic title="每页行数" value={DEFAULT_PAGE_SIZE} suffix="行" prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card className="motion-summary-card">
            <Statistic title="筛选条件" value={activeFilters} suffix="项" prefix={<SyncOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={17}>
          <Card className="table-card" title="A 股股票池">
            <StockFilters
              value={filters}
              syncing={syncMutation.isPending}
              loading={stocksQuery.isFetching}
              sourceOptions={sourceOptions}
              onChange={handleFilterChange}
              onRefresh={() => void stocksQuery.refetch()}
              onSync={handleSync}
            />

            {stocksQuery.isError ? (
              <ErrorState error={stocksQuery.error} onRetry={() => void stocksQuery.refetch()} />
            ) : (
              <StocksTable
                data={stocksQuery.data}
                params={params}
                loading={stocksQuery.isFetching}
                onViewDetails={(stock) => {
                  void navigate({
                    to: '/stocks/$symbol',
                    params: { symbol: stock.symbol },
                    search: { market: normalizeV1Market(stock.market || filters.market) },
                  });
                }}
                onPageChange={(page, pageSize) => {
                  void navigate({
                    search: {
                      keyword: filters.keyword || undefined,
                      industry: filters.industry || undefined,
                      exchange: filters.exchange || undefined,
                      market: filters.market || undefined,
                      status: filters.status || undefined,
                      dailyCoverage: filters.dailyCoverage || undefined,
                      syncSource: filters.syncSource || undefined,
                      page,
                      pageSize,
                    },
                  });
                }}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={7}>
          <RecentSyncTasks />
        </Col>
      </Row>
    </div>
  );
}
