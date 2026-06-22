import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  Col,
  Empty,
  Input,
  List,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  Button,
  Divider,
} from 'antd';
import { SearchOutlined, ReloadOutlined, LinkOutlined } from '@ant-design/icons';
import { fetchNews, type NewsItem } from '../../features/market/api';

const { Text, Paragraph } = Typography;

export function NewsPage() {
  const [keyword, setKeyword] = useState('A股');
  const [inputValue, setInputValue] = useState('A股');

  const newsQuery = useQuery({
    queryKey: ['market', 'news', keyword],
    queryFn: ({ signal }) => fetchNews(keyword, 30, signal),
    refetchInterval: 60_000,
  });

  const handleSearch = useCallback(() => {
    const kw = inputValue.trim();
    if (kw) setKeyword(kw);
  }, [inputValue]);

  const data = newsQuery.data ?? [];
  const isLoading = newsQuery.isLoading && !newsQuery.data;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      {/* Header */}
      <Row justify="space-between" align="middle">
        <Col>
          <Typography.Title level={4} style={{ margin: 0 }}>
            财经新闻
          </Typography.Title>
        </Col>
        <Col>
          <Space>
            <Input
              placeholder="搜索关键词 / 股票代码"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onPressEnter={handleSearch}
              style={{ width: 200 }}
              allowClear
              onClear={() => {
                setInputValue('A股');
                setKeyword('A股');
              }}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
              搜索
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={newsQuery.isFetching}
              onClick={() => newsQuery.refetch()}
            >
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      {/* News list */}
      <Spin spinning={isLoading}>
        {data.length === 0 ? (
          <Empty description={isLoading ? '加载中...' : '暂无新闻'} />
        ) : (
          <List
            dataSource={data}
            renderItem={(item: NewsItem) => (
              <List.Item key={item.url} style={{ padding: '12px 0' }}>
                <Card size="small" style={{ width: '100%' }} hoverable>
                  <Row gutter={[16, 8]}>
                    <Col span={24}>
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <Space split={<Divider type="vertical" />} wrap>
                          <Tag color="blue">{item.source || '新浪'}</Tag>
                          <Text type="secondary">{item.created_at}</Text>
                        </Space>
                        <Typography.Title level={5} style={{ margin: 0 }}>
                          <a href={item.url} target="_blank" rel="noopener noreferrer">
                            {item.title}
                          </a>
                        </Typography.Title>
                        {item.summary && (
                          <Paragraph
                            type="secondary"
                            ellipsis={{ rows: 2 }}
                            style={{ marginBottom: 0 }}
                          >
                            {item.summary}
                          </Paragraph>
                        )}
                        <Button
                          type="link"
                          size="small"
                          icon={<LinkOutlined />}
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ padding: 0 }}
                        >
                          阅读原文
                        </Button>
                      </Space>
                    </Col>
                  </Row>
                </Card>
              </List.Item>
            )}
          />
        )}
      </Spin>
    </Space>
  );
}
