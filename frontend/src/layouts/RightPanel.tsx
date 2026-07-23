import { useQuery } from '@tanstack/react-query';
import { Card, Space, Tag, Typography } from 'antd';
import { useNavigate } from '@tanstack/react-router';
import { apiRequest } from '../shared/api/client';
import { useEffect, useRef } from 'react';
import { gsap } from '../shared/motion/gsapMotion';

type IndexData = { name: string; price: number; change_pct: number };

export function RightPanel() {
  const navigate = useNavigate();
  const ref = useRef<HTMLDivElement>(null);

  const { data: indices } = useQuery({
    queryKey: ['market-index'],
    queryFn: (): Promise<IndexData[]> => apiRequest('/api/market/index'),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (ref.current) {
      gsap.fromTo(ref.current, { opacity: 0, x: 8 }, { opacity: 1, x: 0, duration: 0.3, ease: 'power1.out' });
    }
  }, []);

  return (
    <div ref={ref} className="right-panel-inner">
      {/* 指数快览 */}
      <Card className="rp-card" size="small" title="指数">
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          {(indices ?? []).map((idx) => {
            const up = idx.change_pct >= 0;
            return (
              <div key={idx.name} className="rp-index-row">
                <Typography.Text style={{ fontSize: 12, width: 56, display: 'inline-block' }}>{idx.name}</Typography.Text>
                <span className="tv-number" style={{ color: up ? 'var(--tv-up)' : 'var(--tv-down)', fontSize: 12 }}>
                  {idx.price.toFixed(2)}
                </span>
                <span className={`change-badge ${up ? 'up' : 'down'}`}>{up ? '+' : ''}{idx.change_pct.toFixed(2)}%</span>
              </div>
            );
          })}
        </Space>
      </Card>

      {/* 快捷入口 */}
      <Card className="rp-card" size="small" title="快捷">
        <Space wrap size={4}>
          {[
            { label: '自选股', path: '/watchlist', color: '#2962ff' },
            { label: '股票池', path: '/stocks', color: '#22ab94' },
            { label: '同步', path: '/sync-tasks', color: '#d4941a' },
          ].map((btn) => (
            <Tag key={btn.label} color={btn.color} style={{ cursor: 'pointer', margin: 2 }}
              onClick={() => navigate({ to: btn.path })}>
              {btn.label}
            </Tag>
          ))}
        </Space>
      </Card>

      {/* 数据概览 */}
      <Card className="rp-card" size="small" title="数据">
        <Space direction="vertical" size={3} style={{ width: '100%' }}>
          {[
            { label: '股票', value: '5,877' },
            { label: '日线', value: '107,136' },
            { label: '交易日', value: '52' },
            { label: '行业分类', value: '5,268' },
          ].map((d) => (
            <div key={d.label} className="rp-stat-row">
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>{d.label}</Typography.Text>
              <span className="tv-number" style={{ fontSize: 12 }}>{d.value}</span>
            </div>
          ))}
        </Space>
      </Card>
    </div>
  );
}
