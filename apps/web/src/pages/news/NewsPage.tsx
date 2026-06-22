import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as Icons from '@ant-design/icons';
import { Button, Card, Empty, Input, List, Pagination, Space, Spin, Tag, Typography } from 'antd';
import { fetchNews, type NewsItem } from '../../features/market/api';

const PAGE_SIZE = 10;

export function NewsPage() {
  const [keyword, setKeyword] = useState('A股');
  const [input, setInput] = useState('A股');
  const [page, setPage] = useState(1);
  const { data = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ['market', 'news', keyword, page],
    queryFn: ({ signal }) => fetchNews(keyword, PAGE_SIZE, signal, page),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  });

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>财经新闻</Typography.Title>
        <Space>
          <Input placeholder="搜索关键词" value={input} onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => { setKeyword(input.trim() || 'A股'); setPage(1); }}
            allowClear onClear={() => { setInput('A股'); setKeyword('A股'); setPage(1); }} style={{ width: 200 }} />
          <Button type="primary" icon={<Icons.SearchOutlined />} onClick={() => { setKeyword(input.trim() || 'A股'); setPage(1); }}>搜索</Button>
          <Button icon={<Icons.ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>刷新</Button>
        </Space>
      </Space>

      <Spin spinning={isLoading}>
        {!data.length ? <Empty description={isLoading ? '加载中...' : '暂无新闻'} /> : (
          <>
            <List dataSource={data} renderItem={(item: NewsItem) => (
              <List.Item key={item.url} style={{ padding: '12px 0' }}>
                <Card size="small" style={{ width: '100%' }} hoverable>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Space split={<span style={{ color: '#d9d9d9' }}>|</span>} wrap>
                      <Tag color="blue">{item.source || '新浪'}</Tag>
                      <Typography.Text type="secondary">{item.created_at}</Typography.Text>
                    </Space>
                    <Typography.Title level={5} style={{ margin: 0 }}>
                      <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                    </Typography.Title>
                    {item.summary && <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>{item.summary}</Typography.Paragraph>}
                    <Button type="link" size="small" icon={<Icons.LinkOutlined />} href={item.url} target="_blank" rel="noopener noreferrer" style={{ padding: 0 }}>阅读原文</Button>
                  </Space>
                </Card>
              </List.Item>
            )} />
            <div style={{ textAlign: 'center' }}>
              <Pagination current={page} onChange={setPage} pageSize={PAGE_SIZE} total={100} showSizeChanger={false} />
            </div>
          </>
        )}
      </Spin>
    </Space>
  );
}
