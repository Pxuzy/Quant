import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from '@tanstack/react-router';
import { Card, Segmented, Spin, Typography } from 'antd';
import { createChart, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';
import type { CandlestickData, HistogramData, LineData, Time } from 'lightweight-charts';

const API = '/api/market/kline';

type KlineItem = {
  date: string;
  open: number;
  high: number;
  close: number;
  low: number;
  volume: number;
};

function calcMA(data: KlineItem[], period: number): LineData[] {
  return data.map((d, i) => {
    const slice = data.slice(Math.max(0, i - period + 1), i + 1);
    const avg = slice.reduce((s, x) => s + x.close, 0) / slice.length;
    return { time: d.date as Time, value: +avg.toFixed(2) };
  });
}

export function StockPage() {
  const { code } = useParams({ from: '/stock/$code' });
  const [period, setPeriod] = useState<'day' | 'week' | 'month'>('day');
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState(code.toUpperCase());
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<ReturnType<typeof createChart>>();

  const fetchKline = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}?code=${code}&period=${period}&count=180`);
      const data: KlineItem[] = await res.json();
      if (!data.length) { setLoading(false); return; }
      setName(data[0]?.date ? code.toUpperCase() : code);

      if (!chartRef.current) return;
      const w = chartRef.current.clientWidth;
      const h = chartRef.current.clientHeight || 500;

      // Destroy previous chart if exists
      chartApiRef.current?.remove();
      const chart = createChart(chartRef.current, {
        width: w,
        height: h,
        layout: { background: { color: '#ffffff' }, textColor: '#333' },
        grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
        timeScale: { timeVisible: false, borderColor: '#e0e0e0' },
        rightPriceScale: { borderColor: '#e0e0e0' },
      });
      chartApiRef.current = chart;

      // Candlestick series (A-share: 红涨绿跌)
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#ef5350',
        downColor: '#26a69a',
        borderUpColor: '#ef5350',
        borderDownColor: '#26a69a',
        wickUpColor: '#ef5350',
        wickDownColor: '#26a69a',
      });
      candleSeries.setData(data.map(d => ({
        time: d.date as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      } as CandlestickData)));

      // Volume histogram
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      });
      chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
      volumeSeries.setData(data.map(d => ({
        time: d.date as Time,
        value: d.volume,
        color: d.close >= d.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)',
      } as HistogramData)));

      // MA lines
      if (data.length >= 5) {
        chart.addSeries(LineSeries, { color: '#FF9800', lineWidth: 1, priceLineVisible: false })
          .setData(calcMA(data, 5));
      }
      if (data.length >= 10) {
        chart.addSeries(LineSeries, { color: '#2196F3', lineWidth: 1, priceLineVisible: false })
          .setData(calcMA(data, 10));
      }
      if (data.length >= 20) {
        chart.addSeries(LineSeries, { color: '#9C27B0', lineWidth: 1, priceLineVisible: false })
          .setData(calcMA(data, 20));
      }

      chart.timeScale().fitContent();
    } catch (e) {
      console.error('Kline fetch failed', e);
    }
    setLoading(false);
  }, [code, period]);

  useEffect(() => { fetchKline(); return () => chartApiRef.current?.remove(); }, [fetchKline]);

  // Resize handler
  useEffect(() => {
    const onResize = () => {
      if (!chartRef.current || !chartApiRef.current) return;
      chartApiRef.current.applyOptions({ width: chartRef.current.clientWidth });
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>{name}</Typography.Title>
        <Segmented
          value={period}
          onChange={(v) => setPeriod(v as 'day' | 'week' | 'month')}
          options={[
            { label: '日线', value: 'day' },
            { label: '周线', value: 'week' },
            { label: '月线', value: 'month' },
          ]}
        />
        {loading && <Spin size="small" />}
      </div>
      <Card styles={{ body: { padding: 0 } }} style={{ flex: 1, minHeight: 400 }}>
        <div ref={chartRef} style={{ width: '100%', height: '100%', minHeight: 400 }} />
      </Card>
    </div>
  );
}
