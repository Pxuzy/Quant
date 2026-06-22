import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useParams } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import * as Icons from '@ant-design/icons';
import { Card, Col, Row, Select, Spin, Statistic, Typography, Checkbox, Space, Tag } from 'antd';
import {
  createChart, ColorType, CrosshairMode,
  type IChartApi, type ISeriesApi, type CandlestickData, type HistogramData, type Time,
  CandlestickSeries, HistogramSeries, LineSeries,
} from 'lightweight-charts';
import { fetchKline, fetchQuote, type KLine, type Quote } from '../../features/market/api';

const PERIOD_OPTIONS = [
  { value: 'day', label: '日线' },
  { value: 'week', label: '周线' },
  { value: 'month', label: '月线' },
];

// ponytail: 用 reduce 替代手动循环
const calcMA = (data: KLine[], period: number): { time: Time; value: number }[] => {
  if (data.length < period) return [];
  return data.slice(period - 1).map((d, i) => ({
    time: d.date as Time,
    value: data.slice(i, i + period).reduce((s, x) => s + x.close, 0) / period,
  }));
};

// ponytail: 提取图表 hook，分离关注点
function useKlineChart(klineData: KLine[], showMA: { ma5: boolean; ma10: boolean; ma20: boolean }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const volRef = useRef<HTMLDivElement>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeries = useRef<ISeriesApi<'Histogram'> | null>(null);
  const maLines = useRef<ISeriesApi<'Line'>[]>([]);

  useEffect(() => {
    if (!chartRef.current || !volRef.current) return;
    const chart = createChart(chartRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#fff' }, textColor: '#333' },
      grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#d9d9d9' },
      timeScale: { borderColor: '#d9d9d9' },
      width: chartRef.current.clientWidth, height: 400,
    });
    const volChart = createChart(volRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#fff' }, textColor: '#333' },
      grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
      rightPriceScale: { borderColor: '#d9d9d9' },
      timeScale: { borderColor: '#d9d9d9' },
      width: volRef.current.clientWidth, height: 120,
    });

    candleSeries.current = chart.addSeries(CandlestickSeries, { upColor: '#ef5350', downColor: '#26a69a', borderUpColor: '#ef5350', borderDownColor: '#26a69a', wickUpColor: '#ef5350', wickDownColor: '#26a69a' });
    volSeries.current = volChart.addSeries(HistogramSeries, { color: '#26a69a', priceFormat: { type: 'volume' } });
    volSeries.current.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
    chartApi.current = chart;

    const resize = () => {
      if (chartRef.current) chart.applyOptions({ width: chartRef.current.clientWidth });
      if (volRef.current) volChart.applyOptions({ width: volRef.current.clientWidth });
    };
    window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); chart.remove(); volChart.remove(); };
  }, []);

  useEffect(() => {
    if (!candleSeries.current || !volSeries.current || !klineData.length) return;
    candleSeries.current.setData(klineData.map((d) => ({ time: d.date as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
    volSeries.current.setData(klineData.map((d) => ({ time: d.date as Time, value: d.volume, color: d.close >= d.open ? 'rgba(239,83,80,0.3)' : 'rgba(38,166,154,0.3)' })));

    maLines.current.forEach((s) => s.remove());
    maLines.current = [];
    ([{ k: 'ma5' as const, p: 5, c: '#2196f3' }, { k: 'ma10' as const, p: 10, c: '#ff9800' }, { k: 'ma20' as const, p: 20, c: '#9c27b0' }])
      .filter(({ k }) => showMA[k])
      .forEach(({ p, c }) => {
        if (!chartApi.current) return;
        const s = chartApi.current.addSeries(LineSeries, { color: c, lineWidth: 1, title: `MA${p}` });
        s.setData(calcMA(klineData, p));
        maLines.current.push(s);
      });
    chartApi.current?.timeScale().fitContent();
  }, [klineData, showMA]);

  return { chartRef, volRef, loading: !klineData.length };
}

// ponytail: 提取行情栏为独立组件
function QuoteBar({ quote }: { quote: Quote }) {
  const isUp = quote.change_pct > 0;
  const val = (v: number | undefined | null) => v ?? 0;
  const fields: [string, ReactNode, string?][] = [
    ['现价', val(quote.price).toFixed(2), isUp ? '#ef5350' : '#26a69a'],
    ['涨跌额', val(quote.change).toFixed(2)],
    ['涨跌幅', `${quote.change_pct > 0 ? '+' : ''}${val(quote.change_pct).toFixed(2)}%`],
    ['开盘', val(quote.open).toFixed(2)],
    ['最高', val(quote.high).toFixed(2)],
    ['最低', val(quote.low).toFixed(2)],
    ['昨收', val(quote.prev_close).toFixed(2)],
    ['成交量', String(val(quote.volume))],
  ];
  return (
    <Card size="small">
      <Row gutter={16}>
        {fields.map(([label, value, color]) => (
          <Col span={3} key={label as string}>
            <Statistic title={label as string} value={value as ReactNode} valueStyle={color ? { color, fontSize: label === '现价' ? 24 : undefined } : undefined} />
          </Col>
        ))}
      </Row>
    </Card>
  );
}

export function StockPage() {
  const { code } = useParams({ from: '/stock/$code' });
  const [period, setPeriod] = useState('day');
  const [showMA, setShowMA] = useState({ ma5: true, ma10: true, ma20: false });

  const { data: klineData = [] } = useQuery({ queryKey: ['market', 'kline', code, period], queryFn: ({ signal }) => fetchKline(code, period, 200, signal), refetchInterval: 60_000 });
  const { data: quote } = useQuery({ queryKey: ['market', 'quote', code], queryFn: ({ signal }) => fetchQuote(code, signal), refetchInterval: 30_000 });

  const { chartRef, volRef, loading } = useKlineChart(klineData, showMA);

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Space align="baseline">
            <Typography.Title level={4} style={{ margin: 0 }}>{quote?.name || code}</Typography.Title>
            <Typography.Text type="secondary">{code}</Typography.Text>
            {quote && <Tag color={quote.change_pct > 0 ? 'red' : quote.change_pct < 0 ? 'green' : 'default'}>{(quote.change_pct ?? 0) > 0 ? '+' : ''}{(quote.change_pct ?? 0).toFixed(2)}%</Tag>}
          </Space>
        </Col>
        <Col>
          <Space>
            <Select value={period} onChange={setPeriod} options={PERIOD_OPTIONS} style={{ width: 100 }} />
            {([['ma5', '#2196f3'], ['ma10', '#ff9800'], ['ma20', '#9c27b0']] as const).map(([key, color]) => (
              <Checkbox key={key} checked={showMA[key]} onChange={(e) => setShowMA((p) => ({ ...p, [key]: e.target.checked }))}>
                <span style={{ color }}>MA{key.replace('ma', '')}</span>
              </Checkbox>
            ))}
          </Space>
        </Col>
      </Row>

      {quote && <QuoteBar quote={quote} />}

      <Spin spinning={loading}>
        <Card title="K线图" size="small"><div ref={chartRef} /></Card>
        <Card title="成交量" size="small" style={{ marginTop: 8 }}><div ref={volRef} /></Card>
      </Spin>
    </Space>
  );
}
