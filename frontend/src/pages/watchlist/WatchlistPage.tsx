import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Card, List, Space, Tag, Typography, Empty, Spin, Popconfirm } from 'antd';
import * as Icons from '@ant-design/icons';
import { useNavigate } from '@tanstack/react-router';
import { apiRequest } from '../shared/api/client';

type WatchlistItem = {
  id: number;
  symbol: string;
  note: string | null;
  added_at: string;
};

type StockQuote = {
  code: string;
  name: string;
  price: number;
  change_pct: number;
};

function fetchWatchlist(): Promise<{ items: WatchlistItem[] }> {
  return apiRequest('/api/watchlist');
}

function fetchQuotes(codes: string[]): Promise<StockQuote[]> {
  return apiRequest(`/api/market/quote?codes=${codes.join(',')}`);
}

function addItem(symbol: string) {
  return apiRequest('/api/watchlist/items', { method: 'POST', body: { symbol } });
}

function removeItem(symbol: string) {
  return apiRequest(`/api/watchlist/items/${symbol}`, { method: 'DELETE' });
}

export function WatchlistPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: wl, isLoading } = useQuery({ queryKey: ['watchlist'], queryFn: fetchWatchlist });
  const items = wl?.items ?? [];

  const codes = items.map((i) => i.symbol).join(',');
  const { data: quotes } = useQuery({
    queryKey: ['quotes', codes],
    queryFn: () => fetchQuotes(items.map((i) => `sh${i.symbol}`.replace('shsh', 'sh').replace('szsh', 'sz'))),
    enabled: items.length > 0,
    refetchInterval: 30_000,
  });

  const quoteMap = new Map(quotes?.map((q) => [q.code.replace(/^[a-z]{2}/, ''), q]));

  const del = useMutation({
    mutationFn: removeItem,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  });

  const add = useMutation({
    mutationFn: () => addItem(prompt('输入股票代码（如 600519）') || ''),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  });

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}><Icons.StarOutlined /> 自选股</Typography.Title>
        <Button type="primary" icon={<Icons.PlusOutlined />} onClick={() => add.mutate()} loading={add.isPending}>添加</Button>
      </Space>

      {isLoading ? <Spin /> : items.length === 0 ? (
        <Empty description="还没有自选股，点击「添加」按钮加入第一只" />
      ) : (
        <List
          dataSource={items}
          renderItem={(item) => {
            const q = quoteMap.get(item.symbol) || { name: item.symbol, price: 0, change_pct: 0 };
            const color = q.change_pct >= 0 ? '#f5222d' : '#52c41a';
            return (
              <Card
                size="small"
                style={{ marginBottom: 8, cursor: 'pointer' }}
                onClick={() => navigate({ to: '/stocks/$symbol', params: { symbol: item.symbol } })}
                extra={
                  <Popconfirm title="确定删除？" onConfirm={() => del.mutate(item.symbol)}>
                    <Button size="small" danger icon={<Icons.DeleteOutlined />} />
                  </Popconfirm>
                }
              >
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Space>
                    <Typography.Text strong>{q.name || item.symbol}</Typography.Text>
                    <Tag>{item.symbol}</Tag>
                  </Space>
                  <Space>
                    <Typography.Text style={{ color }}>{q.price.toFixed(2)}</Typography.Text>
                    <Typography.Text style={{ color }}>{q.change_pct >= 0 ? '+' : ''}{q.change_pct.toFixed(2)}%</Typography.Text>
                  </Space>
                </Space>
              </Card>
            );
          }}
        />
      )}
    </div>
  );
}
