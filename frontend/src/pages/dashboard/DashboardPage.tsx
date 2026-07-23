import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App as AntApp,
  Button,
  Card,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  fetchSectorRankings,
  fetchIndexQuotes,
  fetchNews,
  fetchQuotes,
  searchStocks,
  marketQueryKeys,
} from '../../features/market/api';
import type { Quote, SectorRanking } from '../../features/market/api';
import { apiRequest } from '../../shared/api/client';

const REFRESH_OPTIONS = [
  { label: '10秒', value: 10_000 },
  { label: '30秒', value: 30_000 },
  { label: '1分钟', value: 60_000 },
  { label: '5分钟', value: 300_000 },
  { label: '手动', value: 0 },
] as const;

const FAVORITES_KEY = 'quant_dashboard_favorites';
const BOARD_CATEGORIES = ['行业板块', '概念板块', '指数板块'] as const;
type BoardCategory = (typeof BOARD_CATEGORIES)[number];

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

function formatSignedPct(v: number): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function getChangeTone(v: number): 'up' | 'down' | 'flat' {
  if (v > 0) return 'up';
  if (v < 0) return 'down';
  return 'flat';
}

function getTagColor(v: number): 'red' | 'green' | 'default' {
  if (v > 0) return 'red';
  if (v < 0) return 'green';
  return 'default';
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
  const [sector, setSector] = useState('');
  const [selectedBoardCategory, setSelectedBoardCategory] = useState<BoardCategory>('行业板块');
  const [sectorSort, setSectorSort] = useState<'change_pct' | 'amount' | 'volume'>('change_pct');

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
    queryKey: ['market', 'sector', selectedBoardCategory, sector],
    queryFn: ({ signal }) => apiRequest<Quote[]>('/api/market/sector', { name: sector, category: selectedBoardCategory }, { signal }),
    refetchInterval: refreshInterval || false,
    placeholderData: (prev) => prev,
  });

  // Sector rankings
  const sectorRankQuery = useQuery({
    queryKey: [...marketQueryKeys.all, 'sector-rankings', selectedBoardCategory],
    queryFn: ({ signal }) => fetchSectorRankings([selectedBoardCategory], signal),
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
    queryKey: marketQueryKeys.news(''),
    queryFn: ({ signal }) => fetchNews('', 20, signal),
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

  const indexCards = useMemo(() => {
    const data = indexQuery.data ?? [];
    const defaults = [
      { code: 'sh000001', name: '上证指数', price: 0, change: 0, change_pct: 0 },
      { code: 'sz399001', name: '深证成指', price: 0, change: 0, change_pct: 0 },
      { code: 'sh000300', name: '沪深300', price: 0, change: 0, change_pct: 0 },
      { code: 'sz399006', name: '创业板指', price: 0, change: 0, change_pct: 0 },
    ];
    const map = new Map(data.map((d) => [d.code, d]));
    return defaults.map((d) => map.get(d.code) ?? d);
  }, [indexQuery.data]);

  const indexPulse = useMemo(() => {
    const active = indexCards.filter((item) => item.price > 0);
    const rows = active.length > 0 ? active : indexCards;
    const avg = rows.length > 0 ? rows.reduce((sum, item) => sum + item.change_pct, 0) / rows.length : 0;
    return {
      up: rows.filter((item) => item.change_pct > 0).length,
      down: rows.filter((item) => item.change_pct < 0).length,
      flat: rows.filter((item) => item.change_pct === 0).length,
      avg,
    };
  }, [indexCards]);

  const sectorLeader = useMemo(
    () =>
      (sectorQuery.data ?? []).reduce<Quote | undefined>(
        (best, item) => (!best || item.change_pct > best.change_pct ? item : best),
        undefined,
      ),
    [sectorQuery.data],
  );

  const sectorLaggard = useMemo(
    () =>
      (sectorQuery.data ?? []).reduce<Quote | undefined>(
        (best, item) => (!best || item.change_pct < best.change_pct ? item : best),
        undefined,
      ),
    [sectorQuery.data],
  );

  const sectorRankings = useMemo(() => sectorRankQuery.data ?? [], [sectorRankQuery.data]);

  const visibleSectorRankings = useMemo(() => {
    const items = sectorRankings.filter((item) => item.category === selectedBoardCategory);
    return [...items].sort((a, b) => {
      if (sectorSort === 'amount') return (b.amount ?? 0) - (a.amount ?? 0);
      if (sectorSort === 'volume') return (b.volume ?? 0) - (a.volume ?? 0);
      return (b.change_pct ?? 0) - (a.change_pct ?? 0);
    });
  }, [selectedBoardCategory, sectorRankings, sectorSort]);

  const selectedSectorRanking = useMemo(
    () => visibleSectorRankings.find((item) => item.name === sector),
    [sector, visibleSectorRankings],
  );

  const selectedCategory = selectedSectorRanking?.category ?? selectedBoardCategory;
  const isIndexBoard = selectedCategory === '指数板块';

  const sectorOptions = useMemo(() => {
    return visibleSectorRankings.map((item) => ({ label: item.name, value: item.name }));
  }, [visibleSectorRankings]);

  useEffect(() => {
    const first = visibleSectorRankings[0]?.name;
    if (first && !visibleSectorRankings.some((item) => item.name === sector)) {
      setSector(first);
    }
  }, [sector, visibleSectorRankings]);

  const handleSelectBoard = useCallback((item: SectorRanking) => {
    setSelectedBoardCategory(item.category as BoardCategory);
    setSector(item.name);
  }, []);

  const handleSelectCategory = useCallback(
    (category: BoardCategory) => {
      setSelectedBoardCategory(category);
      setSector('');
    },
    [],
  );

  const favoriteSnapshot = useMemo(() => {
    const rows = favQuery.data ?? [];
    const avg = rows.length > 0 ? rows.reduce((sum, item) => sum + item.change_pct, 0) / rows.length : 0;
    return {
      count: rows.length,
      warning: rows.filter((item) => item.change_pct <= -2).length,
      strong: rows.filter((item) => item.change_pct >= 2).length,
      avg,
    };
  }, [favQuery.data]);

  const latestNews = useMemo(() => (newsQuery.data ?? []).slice(0, 6), [newsQuery.data]);

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
                onClick={() => navigate({ to: '/stocks/$symbol', params: { symbol: code } })}
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
          onClick={() => navigate({ to: '/stocks/$symbol', params: { symbol: record.code } })}
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
          {formatSignedPct(v)}
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
          aria-label={`移除 ${record.name}`}
          onClick={() => removeFavorite(record.code)}
        />
      ),
    },
  ];

  const sectorColumns = [
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 100,
      render: (code: string) => (
        <Typography.Text
          code
          style={{ cursor: 'pointer', color: '#1677ff' }}
                onClick={() => navigate({ to: '/stocks/$symbol', params: { symbol: code } })}
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
      render: (name: string, record: Quote) => (
        <Typography.Text
          style={{ cursor: 'pointer', color: '#1677ff' }}
          onClick={() => navigate({ to: '/stocks/$symbol', params: { symbol: record.code } })}
        >
          {name}
        </Typography.Text>
      ),
    },
    {
      title: '板块',
      dataIndex: 'sectors',
      key: 'sectors',
      width: 100,
      render: (sectors: string[] | undefined) => (
        <Space size={[2, 2]} wrap>
          {(sectors ?? []).slice(0, 2).map((s) => (
            <Tag key={s} color="blue" style={{ fontSize: 10, margin: 0, padding: '0 3px' }}>{s}</Tag>
          ))}
        </Space>
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
          {formatSignedPct(v)}
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

  const isLoading = indexQuery.isLoading && !indexQuery.data;

  return (
    <div className="dashboard-page page-enter">
      <div className="dashboard-toolbar">
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
        {/* Top trader ticker — horizontal index strip, 4 columns no border */}
        <div className="dashboard-ticker" aria-label="指数快览">
          {indexCards.map((idx) => {
            const tone = getChangeTone(idx.change_pct);
            return (
              <div className={`dashboard-ticker-cell is-${tone}`} key={idx.code}>
                <div>
                  <div className="name">{idx.name}</div>
                  <div className="price">
                    {idx.price > 0 ? idx.price.toFixed(2) : '--'}
                  </div>
                </div>
                <div className="meta">
                  <Tag color={idx.change_pct > 0 ? 'red' : idx.change_pct < 0 ? 'green' : 'default'}>
                    {formatSignedPct(idx.change_pct)}
                  </Tag>
                  <span>{idx.change > 0 ? '+' : ''}{idx.change.toFixed(2)}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="dashboard-monitor-grid">
          <aside className="dashboard-monitor-left">
            <Card
              className="dashboard-panel tv-card"
              size="small"
              title="板块排行"
              extra={
                <Space size="small">
                  <Select
                    value={sectorSort}
                    onChange={(v) => setSectorSort(v)}
                    size="small"
                    style={{ width: 90 }}
                    options={[
                      { label: '涨跌幅', value: 'change_pct' },
                      { label: '成交额', value: 'amount' },
                      { label: '成交量', value: 'volume' },
                    ]}
                  />
                  <Typography.Text type="secondary">排序</Typography.Text>
                </Space>
              }
              loading={sectorRankQuery.isLoading}
            >
              <div className="dashboard-rank-board">
                <div className="dashboard-category-tabs" role="tablist" aria-label="板块分类">
                  {BOARD_CATEGORIES.map((category) => (
                    <button
                      aria-selected={selectedBoardCategory === category}
                      className={selectedBoardCategory === category ? 'is-active' : ''}
                      key={category}
                      onClick={() => handleSelectCategory(category)}
                      role="tab"
                      type="button"
                    >
                      {category}
                    </button>
                  ))}
                  <Typography.Text type="secondary" style={{ fontSize: 11, padding:'0 4px', alignSelf:'center' }}>
                    {visibleSectorRankings.length}个
                  </Typography.Text>
                </div>
                <div className="dashboard-rank-head">
                  <span>排名</span>
                  <span>板块</span>
                  <span>涨跌幅</span>
                  <span>成交额</span>
                </div>
                {visibleSectorRankings.map((item: SectorRanking, index) => (
                  <button
                    className={`dashboard-rank-row ${item.name === sector ? 'is-active' : ''}`}
                    key={`${item.category}-${item.name}`}
                    type="button"
                    onClick={() => handleSelectBoard(item)}
                  >
                    <span>{index + 1}</span>
                    <strong>
                      <b>{item.name}</b>
                      <small>
                        {item.stock_count}只 · {item.up_count}/{item.down_count} · {item.leader?.name ?? '暂无领涨'}
                      </small>
                    </strong>
                    <em className={`is-${getChangeTone(item.change_pct)}`}>{formatSignedPct(item.change_pct)}</em>
                    <em className="dashboard-rank-amount">{formatAmount(item.amount)}</em>
                  </button>
                ))}
                {visibleSectorRankings.length === 0 && <Typography.Text type="secondary">暂无{selectedBoardCategory}</Typography.Text>}
              </div>
            </Card>
          </aside>

          <section className="dashboard-monitor-main">
            <Card
              className="dashboard-panel dashboard-workspace-panel"
              size="small"
              title={
                <Space size="small">
                  <span>{isIndexBoard ? '指数行情' : '板块成份股'}</span>
                  <Select
                    value={sector}
                    onChange={setSector}
                    size="small"
                    showSearch
                    filterOption={(input, option) =>
                      (option?.label as string ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    style={{ width: 220 }}
                    options={sectorOptions}
                  />
                </Space>
              }
              extra={
                <Space size="small">
                  {selectedSectorRanking && (
                    <Tag color={getTagColor(selectedSectorRanking.change_pct)}>
                      {formatSignedPct(selectedSectorRanking.change_pct)}
                    </Tag>
                  )}
                  <Typography.Text type="secondary">{(sectorQuery.data ?? []).length}只</Typography.Text>
                </Space>
              }
            >
              <Table className="tv-table"
                dataSource={sectorQuery.data ?? []}
                columns={sectorColumns}
                rowKey="code"
                size="small"
                pagination={false}
                scroll={{ x: 650, y: 440 }}
                loading={sectorQuery.isLoading}
              />
            </Card>
          </section>

          <aside className="dashboard-monitor-right">
            <Card
              className="dashboard-panel tv-card"
              size="small"
              title="自选监控"
              extra={
                <Input.Search
                  placeholder="代码/名称"
                  size="small"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onSearch={handleSearch}
                  loading={searchLoading}
                  style={{ width: 156 }}
                />
              }
            >
              {searchResults.length > 0 && (
                <div className="dashboard-search-results">
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>搜索结果：</Typography.Text>
                  <Space wrap size={[4, 4]}>
                    {searchResults.map((r) => (
                      <Tag
                        key={r.code}
                        color={favorites.includes(r.code) ? 'default' : 'blue'}
                        onClick={() => addFavorite(r.code)}
                      >
                        + {r.name} {r.code}
                      </Tag>
                    ))}
                  </Space>
                </div>
              )}

              <Table className="tv-table"
                dataSource={favQuery.data ?? []}
                columns={favColumns}
                rowKey="code"
                size="small"
                pagination={false}
                scroll={{ x: 520, y: 132 }}
                loading={favQuery.isLoading}
                locale={{ emptyText: '暂无自选股，请搜索添加' }}
              />
            </Card>

            <Card className="dashboard-panel tv-card" size="small" title="预警与操作">
              <div className="dashboard-alert-list">
                <div className="dashboard-alert-row">
                  <strong>指数涨跌</strong>
                  <span className={`is-${getChangeTone(indexPulse.avg)}`}>{indexPulse.up}/{indexPulse.down} · 均值 {formatSignedPct(indexPulse.avg)}</span>
                </div>
                <div className="dashboard-alert-row">
                  <strong>自选预警</strong>
                  <span className={`is-${getChangeTone(favoriteSnapshot.avg)}`}>{favoriteSnapshot.warning}只 · 均值 {formatSignedPct(favoriteSnapshot.avg)}</span>
                </div>
                <div className="dashboard-alert-row">
                  <strong>{isIndexBoard ? '指数领涨' : '板块内领涨'}</strong>
                  <span className={sectorLeader ? `is-${getChangeTone(sectorLeader.change_pct)}` : ''}>
                    {sectorLeader ? `${sectorLeader.name} ${formatSignedPct(sectorLeader.change_pct)}` : '等待数据'}
                  </span>
                </div>
                <div className="dashboard-alert-row">
                  <strong>{isIndexBoard ? '指数领跌' : '板块内领跌'}</strong>
                  <span className={sectorLaggard ? `is-${getChangeTone(sectorLaggard.change_pct)}` : ''}>
                    {sectorLaggard ? `${sectorLaggard.name} ${formatSignedPct(sectorLaggard.change_pct)}` : '等待数据'}
                  </span>
                </div>
              </div>
            </Card>

            <Card className="dashboard-panel dashboard-admin-panel" size="small" title="快捷入口">
              <div className="dashboard-admin-actions">
                <Button size="small" icon={<ApiOutlined />} onClick={() => navigate({ to: '/data-system/data-sources' })}>数据源</Button>
                <Button size="small" icon={<SyncOutlined />} onClick={() => navigate({ to: '/data-system/pipeline' })}>数据链路</Button>
                <Button size="small" icon={<CloudSyncOutlined />} onClick={() => navigate({ to: '/sync-tasks' })}>同步调度</Button>
                <Button size="small" icon={<DatabaseOutlined />} onClick={() => navigate({ to: '/database' })}>数据库管理</Button>
                <Button size="small" icon={<WarningOutlined />} onClick={() => navigate({ to: '/alerts' })}>异常中心</Button>
              </div>
            </Card>

            <Card className="dashboard-panel dashboard-news-panel" size="small" title="新闻快扫" loading={newsQuery.isLoading}>
              <div className="dashboard-news-list dashboard-news-list-compact">
                {latestNews.slice(0, 4).map((item) => (
                  <a className="dashboard-news-item" href={item.url} target="_blank" rel="noopener noreferrer" key={item.url}>
                    <span>{item.title}</span>
                    <em>{item.source}</em>
                  </a>
                ))}
                {latestNews.length === 0 && <Typography.Text type="secondary">暂无新闻</Typography.Text>}
              </div>
            </Card>
          </aside>
        </div>
      </Spin>
    </div>
  );
}
