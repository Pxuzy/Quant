import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Divider,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  StarFilled,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  fetchIndexQuotes,
  fetchNews,
  fetchQuotes,
  searchStocks,
  marketQueryKeys,
} from '../../features/market/api';
import type { Quote, NewsItem } from '../../features/market/api';
import { apiRequest } from '../../shared/api/client';

const REFRESH_OPTIONS = [
  { label: '10秒', value: 10_000 },
  { label: '30秒', value: 30_000 },
  { label: '1分钟', value: 60_000 },
  { label: '5分钟', value: 300_000 },
  { label: '手动', value: 0 },
] as const;

const FAVORITES_KEY = 'quant_dashboard_favorites';

function loadFavorites(): string[] {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    return raw ? JSON.parse(raw) : ['sh600900', 'sz000858', 'sh601398', 'sz000001'];
  } catch {
    return ['sh600900', 'sz000858', 'sh601398', 'sz000001'];
  }
}

function saveFavorites(codes: string[]) {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(codes));
}

function formatVolume(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return String(v);
}

function formatAmount(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return v.toFixed(2);
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();

  const [favorites, setFavorites] = useState<string[]>(loadFavorites);
  const [refreshInterval, setRefreshInterval] = useState<number>(30_000);
  const [searchInput, setSearchInput] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [sector, setSector] = useState('电力');

  useEffect(() => {
    saveFavorites(favorites);
  }, [favorites]);

  // Index quotes
  const indexQuery = useQuery({
    queryKey: marketQueryKeys.index(),
    queryFn: ({ signal }) => fetchIndexQuotes(signal),
    refetchInterval: refreshInterval || false,
    placeholderData: (prev) => prev,
  });

  // Sector stocks
  const sectorQuery = useQuery({
    queryKey: ['market', 'sector', sector],
    queryFn: ({ signal }) => apiRequest<Quote[]>(`/api/market/sector?name=${encodeURIComponent(sector)}`, undefined, { signal }),
    refetchInterval: refreshInterval || false,
    placeholderData: (prev) => prev,
  });

  // Favorites quotes
  const favQuery = useQuery({
    queryKey: marketQueryKeys.quotes(favorites),
    queryFn: ({ signal }) => (favorites.length > 0 ? fetchQuotes(favorites, signal) : Promise.resolve([])),
    refetchInterval: refreshInterval || false,
    placeholderData: (prev) => prev,
    enabled: favorites.length > 0,
  });

  // News
  const newsQuery = useQuery({
    queryKey: marketQueryKeys.news('A股'),
    queryFn: ({ signal }) => fetchNews('A股', 20, signal),
    refetchInterval: refreshInterval || false,
    placeholderData: (prev) => prev,
  });

  const handleSearch = useCallback(async (value: string) => {
    const keyword = value.trim();
    if (!keyword) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const results = await searchStocks(keyword);
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, []);

  const addFavorite = useCallback(
    (code: string) => {
      if (favorites.includes(code)) {
        void message.info('已在自选股中');
        return;
      }
      setFavorites((prev) => [...prev, code]);
      setSearchInput('');
      setSearchResults([]);
      void message.success(`已添加 ${code}`);
    },
    [favorites, message],
  );

  const removeFavorite = useCallback(
    (code: string) => {
      setFavorites((prev) => prev.filter((c) => c !== code));
      void message.success(`已移除 ${code}`);
    },
    [message],
  );

  const refreshAll = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: marketQueryKeys.all });
  }, [queryClient]);

  // --- Index cards ---
  const indexCards = useMemo(() => {
    const data = indexQuery.data ?? [];
    // Default 4 cards if no data
    const defaults = [
      { code: 'sh000001', name: '上证指数', price: 0, change: 0, change_pct: 0 },
      { code: 'sz399001', name: '深证成指', price: 0, change: 0, change_pct: 0 },
      { code: 'sh000300', name: '沪深300', price: 0, change: 0, change_pct: 0 },
      { code: 'sz399006', name: '创业板指', price: 0, change: 0, change_pct: 0 },
    ];
    const map = new Map(data.map((d) => [d.code, d]));
    return defaults.map((d) => map.get(d.code) ?? d);
  }, [indexQuery.data]);

  // --- Favorite stocks table columns ---
  const favColumns = [
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 100,
      render: (code: string) => (
        <Typography.Text
          code
          style={{ cursor: 'pointer', color: '#1677ff' }}
          onClick={() => navigate({ to: '/stock/$code', params: { code } })}
        >
          {code}
        </Typography.Text>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 100,
      render: (_: string, record: Quote) => (
        <Typography.Text
          style={{ cursor: 'pointer', color: '#1677ff' }}
          onClick={() => navigate({ to: '/stock/$code', params: { code: record.code } })}
        >
          {record.name}
        </Typography.Text>
      ),
    },
    {
      title: '最新价',
      dataIndex: 'price',
      key: 'price',
      width: 90,
      render: (v: number) => v.toFixed(2),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 90,
      render: (v: number) => (
        <Tag color={v > 0 ? 'red' : v < 0 ? 'green' : 'default'}>
          {v > 0 ? '+' : ''}{v.toFixed(2)}%
        </Tag>
      ),
    },
    {
      title: '成交额',
      dataIndex: 'amount',
      key: 'amount',
      width: 100,
      render: (v: number) => formatAmount(v),
    },
    {
      title: '操作',
      key: 'action',
      width: 60,
      render: (_: unknown, record: Quote) => (
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => removeFavorite(record.code)}
        />
      ),
    },
  ];

  // --- Sector table columns ---
  const sectorColumns = [
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 100,
      render: (code: string) => <Typography.Text code>{code}</Typography.Text>,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 100,
    },
    {
      title: '最新价',
      dataIndex: 'price',
      key: 'price',
      width: 90,
      render: (v: number) => v.toFixed(2),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 90,
      render: (v: number) => (
        <Tag color={v > 0 ? 'red' : v < 0 ? 'green' : 'default'}>
          {v > 0 ? '+' : ''}{v.toFixed(2)}%
        </Tag>
      ),
    },
    {
      title: '成交量',
      dataIndex: 'volume',
      key: 'volume',
      width: 100,
      render: (v: number) => formatVolume(v),
    },
    {
      title: 'PE',
      dataIndex: 'pe',
      key: 'pe',
      width: 70,
      render: (v: number) => (v > 0 ? v.toFixed(1) : '-'),
    },
  ];

  // --- News table columns ---
  const newsColumns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record: NewsItem) => (
        <a href={record.url} target="_blank" rel="noopener noreferrer">
          {title}
        </a>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 100,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
    },
  ];

  const isLoading = indexQuery.isLoading && !indexQuery.data;

  return (
    <div style={{ padding: '16px 24px', background: '#f5f5f5', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          市场行情仪表盘
        </Typography.Title>
        <Space>
          <Select
            value={refreshInterval}
            onChange={(v) => setRefreshInterval(v)}
            options={REFRESH_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
            style={{ width: 100 }}
            size="small"
          />
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={refreshAll}
            loading={indexQuery.isFetching}
          >
            刷新
          </Button>
        </Space>
      </div>

      <Spin spinning={isLoading}>
        {/* Index Cards Row */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {indexCards.map((idx) => {
            const isUp = idx.change_pct > 0;
            const isDown = idx.change_pct < 0;
            return (
              <Col xs={24} sm={12} md={6} key={idx.code}>
                <Card size="small" style={{ borderTop: `3px solid ${isUp ? '#ff4d4f' : isDown ? '#52c41a' : '#d9d9d9'}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{idx.name}</Typography.Text>
                      <div style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.3 }}>
                        {idx.price > 0 ? idx.price.toFixed(2) : '--'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <Tag color={isUp ? 'red' : isDown ? 'green' : 'default'} style={{ marginRight: 0 }}>
                        {idx.change_pct > 0 ? '+' : ''}{idx.change_pct.toFixed(2)}%
                      </Tag>
                      <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                        {idx.change > 0 ? '+' : ''}{idx.change.toFixed(2)}
                      </div>
                    </div>
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>

        {/* Middle: Sector + Favorites */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} lg={14}>
            <Card
              size="small"
              title={
                <Space>
                  <span>板块行情</span>
                  <Select
                    value={sector}
                    onChange={setSector}
                    size="small"
                    style={{ width: 100 }}
                    options={[
                      { label: '电力', value: '电力' },
                      { label: '煤炭', value: '煤炭' },
                      { label: '银行', value: '银行' },
                    ]}
                  />
                </Space>
              }
            >
              <Table
                dataSource={sectorQuery.data ?? []}
                columns={sectorColumns}
                rowKey="code"
                size="small"
                pagination={false}
                scroll={{ y: 320 }}
                loading={sectorQuery.isLoading}
              />
            </Card>
          </Col>

          <Col xs={24} lg={10}>
            <Card
              size="small"
              title="自选股"
              extra={
                <Space size="small">
                  <Input.Search
                    placeholder="搜索股票代码/名称"
                    size="small"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    onSearch={handleSearch}
                    loading={searchLoading}
                    style={{ width: 200 }}
                  />
                </Space>
              }
            >
              {/* Search results dropdown */}
              {searchResults.length > 0 && (
                <div style={{ marginBottom: 8, padding: 8, background: '#fafafa', borderRadius: 4, border: '1px solid #f0f0f0' }}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>搜索结果：</Typography.Text>
                  <Space wrap size={[4, 4]} style={{ marginTop: 4 }}>
                    {searchResults.map((r) => (
                      <Tag
                        key={r.code}
                        style={{ cursor: 'pointer' }}
                        color={favorites.includes(r.code) ? 'default' : 'blue'}
                        icon={favorites.includes(r.code) ? <StarFilled /> : <PlusOutlined />}
                        onClick={() => addFavorite(r.code)}
                      >
                        {r.name} ({r.code})
                      </Tag>
                    ))}
                  </Space>
                </div>
              )}

              <Table
                dataSource={favQuery.data ?? []}
                columns={favColumns}
                rowKey="code"
                size="small"
                pagination={false}
                scroll={{ y: 320 }}
                loading={favQuery.isLoading}
                locale={{ emptyText: '暂无自选股，请搜索添加' }}
              />
            </Card>
          </Col>
        </Row>

        {/* News */}
        <Card size="small" title="财经要闻" style={{ marginBottom: 16 }}>
          <Table
            dataSource={newsQuery.data ?? []}
            columns={newsColumns}
            rowKey="url"
            size="small"
            pagination={{ pageSize: 10, size: 'small' }}
            loading={newsQuery.isLoading}
          />
        </Card>

        {/* Data Admin Quick Access */}
        <Card size="small" title="数据后台" style={{ marginBottom: 16 }}>
          <Row gutter={[12, 12]}>
            <Col>
              <Button
                icon={<ApiOutlined />}
                onClick={() => navigate({ to: '/data-sources' })}
              >
                数据源
              </Button>
            </Col>
            <Col>
              <Button
                icon={<SyncOutlined />}
                onClick={() => navigate({ to: '/data-system/pipeline' })}
              >
                数据链路
              </Button>
            </Col>
            <Col>
              <Button
                icon={<CloudSyncOutlined />}
                onClick={() => navigate({ to: '/data-system/sync-tasks' })}
              >
                同步调度
              </Button>
            </Col>
            <Col>
              <Button
                icon={<DatabaseOutlined />}
                onClick={() => navigate({ to: '/data-system/database' })}
              >
                数据库管理
              </Button>
            </Col>
            <Col>
              <Button
                icon={<WarningOutlined />}
                onClick={() => navigate({ to: '/data-system/alerts' })}
              >
                异常中心
              </Button>
            </Col>
          </Row>
        </Card>
      </Spin>
    </div>
  );
}
