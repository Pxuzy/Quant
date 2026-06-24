import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as Icons from '@ant-design/icons';
import { Button, Card, Collapse, Empty, Input, List, Space, Spin, Tag, Typography } from 'antd';
import { fetchNews, type NewsItem } from '../../features/market/api';

const PAGE_SIZE = 50; // fetch enough to cover all sources with overflow
const PREVIEW = 3;    // top-N shown when collapsed (per spec: 前 3 条)
const COLLAPSE_STYLE = {
  background: 'transparent',
  border: 'none',
};
const PANEL_STYLE = {
  background: 'transparent',
  border: 'none',
  marginBottom: 10,
};

const SOURCE_COLOR: Record<string, string> = {
  '新浪港股': 'blue',
  '环球市场播报': 'red',
  '市场资讯': 'purple',
  '智通财经APP': 'orange',
  '21世纪经济报道': 'cyan',
  '环球网': 'magenta',
  '滚动播报': 'gold',
  '每日经济新闻': 'green',
  '澎湃新闻': 'geekblue',
};

const PLACEHOLDER = '未知来源';

function NewsList({ items }: { items: NewsItem[] }) {
  return (
    <List
      size="small"
      split
      dataSource={items}
      renderItem={(item: NewsItem) => (
        <List.Item style={{ padding: '7px 0', borderBlockEnd: 'none' }}>
          <Space direction="vertical" size={3} style={{ width: '100%' }}>
            <Typography.Text style={{ fontSize: 15, lineHeight: 1.45, fontWeight: 500 }}>
              <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
            </Typography.Text>
            <Space size={6}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {item.created_at}
              </Typography.Text>
              {item.category && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  · {item.category}
                </Typography.Text>
              )}
            </Space>
          </Space>
        </List.Item>
      )}
    />
  );
}

export function NewsPage() {
  const [keyword, setKeyword] = useState('A股');
  const [input, setInput] = useState('A股');
  // Track which cards are expanded; default to empty (all collapsed)
  const [expanded, setExpanded] = useState<string[]>([]);

  const { data = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ['market', 'news', keyword],
    queryFn: ({ signal }) => fetchNews(keyword, PAGE_SIZE, signal, 1),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  });

  // Group by source, sorted by count desc
  const grouped = useMemo(() => {
    const m = new Map<string, NewsItem[]>();
    for (const item of data) {
      const src = (item.source || PLACEHOLDER).trim() || PLACEHOLDER;
      if (!m.has(src)) m.set(src, []);
      m.get(src)!.push(item);
    }
    return Array.from(m.entries())
      .sort((a, b) => b[1].length - a[1].length);
  }, [data]);

  // generated item titles count of total in expanded state
  const totalExpanded = expanded.length;
  const onChange = (keys: string | string[]) =>
    setExpanded(Array.isArray(keys) ? keys : [keys]);

  const runSearch = () => {
    const v = input.trim();
    setKeyword(v || 'A股');
    setExpanded([]); // reset on new search
  };

  const headAction = (
    <Space>
      <Input
        placeholder="搜索关键词"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onPressEnter={runSearch}
        allowClear
        onClear={() => { setInput('A股'); setKeyword('A股'); setExpanded([]); }}
        style={{ width: 200 }}
      />
      <Button type="primary" icon={<Icons.SearchOutlined />} onClick={runSearch}>搜索</Button>
      <Button icon={<Icons.ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>刷新</Button>
    </Space>
  );

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%', padding: 16 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>财经新闻 · 平台聚合</Typography.Title>
        {headAction}
      </Space>

      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        关键词「{keyword}」 · 共 {data.length} 条 · {grouped.length} 个平台
        {totalExpanded > 0 && ` · 已展开 ${totalExpanded} 个`}
      </Typography.Text>

      <Spin spinning={isLoading}>
        {!data.length ? (
          <Empty description={isLoading ? '加载中...' : '暂无新闻'} />
        ) : (
          <Collapse
            accordion={false}
            activeKey={expanded}
            onChange={onChange}
            style={COLLAPSE_STYLE}
            items={grouped.map(([src, items]) => ({
              key: src,
              style: PANEL_STYLE,
              label: (
                <Space size="small" wrap>
                  <Tag color={SOURCE_COLOR[src] ?? 'default'} style={{ marginInlineEnd: 0, fontSize: 13 }}>
                    {src}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                    × {items.length}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    前 {Math.min(PREVIEW, items.length)} 条，展开看全部
                  </Typography.Text>
                </Space>
              ),
              children: (
                <Card size="small" className="news-source-card" bordered={false}>
                  <NewsList items={items.slice(0, PREVIEW)} />
                  {items.length > PREVIEW && (
                    <div style={{ marginTop: 8 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        —— 以下为展开后余 {items.length - PREVIEW} 条 ——
                      </Typography.Text>
                      <NewsList items={items.slice(PREVIEW)} />
                    </div>
                  )}
                </Card>
              ),
            }))}
          />
        )}
      </Spin>
    </Space>
  );
}
