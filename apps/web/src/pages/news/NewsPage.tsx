import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as Icons from '@ant-design/icons';
import { Button, Checkbox, Empty, Input, Space, Spin, Tag, Typography } from 'antd';
import { fetchNews, type NewsItem } from '../../features/market/api';

const PAGE_SIZE = 50;
const STEP = 20; // "加载更多" each load

const SOURCE_COLOR: Record<string, string> = {
  '新浪港股': 'volcano',
  '环球市场播报': 'green',
  '市场资讯': 'purple',
  '智通财经APP': 'orange',
  '21世纪经济报道': 'cyan',
  '环球网': 'magenta',
  '滚动播报': 'gold',
  '每日经济新闻': 'lime',
  '澎湃新闻': 'geekblue',
};

const CATEGORIES = ['全部', '市场', '行业', '公司'];
const PLACEHOLDER = '未知来源';

export function NewsPage() {
  const [keyword, setKeyword] = useState('A股');
  const [input, setInput] = useState('A股');
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [category, setCategory] = useState('全部');
  const [showCount, setShowCount] = useState(STEP);

  const { data = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ['market', 'news', keyword],
    queryFn: ({ signal }) => fetchNews(keyword, PAGE_SIZE, signal, 1),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  });

  // Group sources for sidebar
  const sourceCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const item of data) {
      const src = (item.source || PLACEHOLDER).trim() || PLACEHOLDER;
      m.set(src, (m.get(src) || 0) + 1);
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [data]);

  // Filter by source + category
  const filtered = useMemo(() => {
    let items = data;
    if (selectedSources.length > 0) {
      items = items.filter((item) => selectedSources.includes(item.source?.trim() || PLACEHOLDER));
    }
    if (category !== '全部') {
      items = items.filter((item) => item.category === category);
    }
    return items;
  }, [data, selectedSources, category]);

  const visible = useMemo(() => filtered.slice(0, showCount), [filtered, showCount]);
  const hasMore = visible.length < filtered.length;

  const runSearch = () => {
    const v = input.trim();
    setKeyword(v || 'A股');
    setShowCount(STEP);
  };

  const toggleSource = useCallback((src: string) => {
    setSelectedSources((prev) =>
      prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src],
    );
    setShowCount(STEP);
  }, []);

  const resetFilters = useCallback(() => {
    setSelectedSources([]);
    setCategory('全部');
    setShowCount(STEP);
  }, []);

  const hasFilters = selectedSources.length > 0 || category !== '全部';

  return (
    <div className="tv-news-page">
      {/* Header */}
      <div className="tv-news-header">
        <div className="tv-news-header-left">
          <Typography.Title level={4} style={{ margin: 0 }}>财经新闻</Typography.Title>
          <Typography.Text type="secondary" className="tv-news-stats">
            关键词「{keyword}」· {filtered.length}/{data.length} 条 · {sourceCounts.length} 个平台
            {hasFilters && (
              <Button type="link" size="small" onClick={resetFilters} style={{ padding: 0, fontSize: 12 }}>
                清除过滤
              </Button>
            )}
          </Typography.Text>
        </div>
        <Space>
          <Input
            placeholder="搜索关键词"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={runSearch}
            allowClear
            onClear={() => { setInput('A股'); setKeyword('A股'); setShowCount(STEP); }}
            style={{ width: 180 }}
            size="small"
          />
          <Button type="primary" icon={<Icons.SearchOutlined />} onClick={runSearch} size="small">搜索</Button>
          <Button icon={<Icons.ReloadOutlined />} loading={isFetching} onClick={() => refetch()} size="small">刷新</Button>
        </Space>
      </div>

      <div className="tv-news-body">
        {/* Left sidebar — TV's "Top providers" */}
        <aside className="tv-news-sidebar">
          <div className="tv-news-sidebar-head">
            <Typography.Text strong style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              平台过滤
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {sourceCounts.length} 个
            </Typography.Text>
          </div>
          <div className="tv-news-sidebar-list">
            {sourceCounts.map(([src, count]) => (
              <label
                key={src}
                className={`tv-news-src-item ${selectedSources.includes(src) ? 'is-active' : ''}`}
                onClick={() => toggleSource(src)}
              >
                <Checkbox checked={selectedSources.includes(src)} />
                <Tag color={SOURCE_COLOR[src] ?? 'default'} style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}>
                  {src}
                </Tag>
                <span className="tv-news-src-count">{count}</span>
              </label>
            ))}
            {sourceCounts.length === 0 && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无平台</Typography.Text>
            )}
          </div>
        </aside>

        {/* Main content */}
        <main className="tv-news-main">
          {/* Category tabs */}
          <div className="tv-news-tabs" role="tablist">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                role="tab"
                aria-selected={category === cat}
                className={`tv-news-tab ${category === cat ? 'is-active' : ''}`}
                onClick={() => { setCategory(cat); setShowCount(STEP); }}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* News list */}
          <Spin spinning={isLoading}>
            {!filtered.length ? (
              <Empty description={isLoading ? '加载中...' : '暂无匹配新闻'} style={{ marginTop: 40 }} />
            ) : (
              <>
                <div className="tv-news-list">
                  {visible.map((item, idx) => (
                    <a
                      key={`${item.url}-${idx}`}
                      className="tv-news-row"
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <div className="tv-news-row-title">{item.title}</div>
                      <div className="tv-news-row-meta">
                        {item.source && (
                          <Tag color={SOURCE_COLOR[item.source.trim()] ?? 'default'} style={{ margin: 0, fontSize: 10, lineHeight: '16px' }}>
                            {item.source.trim()}
                          </Tag>
                        )}
                        {item.created_at && (
                          <span className="tv-news-row-time">{item.created_at}</span>
                        )}
                        {item.category && (
                          <span className="tv-news-row-cat">{item.category}</span>
                        )}
                      </div>
                    </a>
                  ))}
                </div>
                {hasMore && (
                  <div className="tv-news-more-wrap">
                    <Button
                      type="default"
                      onClick={() => setShowCount((c) => c + STEP)}
                      className="tv-news-more"
                    >
                      加载更多 · 已显示 {visible.length}/{filtered.length} 条
                    </Button>
                  </div>
                )}
              </>
            )}
          </Spin>
        </main>
      </div>
    </div>
  );
}
