import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from '@tanstack/react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Card,
  Col,
  Descriptions,
  message,
  Row,
  Select,
  Spin,
  Statistic,
  Typography,
  Checkbox,
  Space,
  Tag,
} from 'antd';
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts';
import {
  fetchKline,
  fetchQuotes,
  type KLine,
  type Quote,
} from '../../features/market/api';

const PERIOD_OPTIONS = [
  { value: 'day', label: '日线' },
  { value: 'week', label: '周线' },
  { value: 'month', label: '月线' },
];

function calcMA(data: KLine[], period: number): { time: Time; value: number }[] {
  if (data.length < period) return [];
  const result: { time: Time; value: number }[] = [];
  for (let i = period - 1; i < data.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close;
    }
    result.push({ time: data[i].date as Time, value: sum / period });
  }
  return result;
}

export function StockPage() {
  const { code } = useParams({ from: '/stock/$code' });
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<string>('day');
  const [showMA, setShowMA] = useState({ ma5: true, ma10: true, ma20: false });

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const volumeContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const maSeriesRef = useRef<ISeriesApi<'Line'>[]>([]);

  const klineQuery = useQuery({
    queryKey: ['market', 'kline', code, period],
    queryFn: ({ signal }) => fetchKline(code, period, 200, signal),
    refetchInterval: 60_000,
  });

  const quoteQuery = useQuery({
    queryKey: ['market', 'quote', code],
    queryFn: ({ signal }) => fetchQuote(code, signal),
    refetchInterval: 30_000,
    enabled: !!code,
  });

  const quote = quoteQuery.data;
  const klineData = klineQuery.data ?? [];

  // Create chart
  useEffect(() => {
    if (!chartContainerRef.current || !volumeContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#d9d9d9' },
      timeScale: { borderColor: '#d9d9d9' },
      width: chartContainerRef.current.clientWidth,
      height: 400,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ef5350',
      downColor: '#26a69a',
      borderUpColor: '#ef5350',
      borderDownColor: '#26a69a',
      wickUpColor: '#ef5350',
      wickDownColor: '#26a69a',
    });

    const volumeChart = createChart(volumeContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      rightPriceScale: { borderColor: '#d9d9d9' },
      timeScale: { borderColor: '#d9d9d9' },
      width: volumeContainerRef.current.clientWidth,
      height: 120,
    });

    const volumeSeries = volumeChart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.1, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
      if (volumeContainerRef.current) {
        volumeChart.applyOptions({ width: volumeContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      volumeChart.remove();
    };
  }, [code, period]);

  // Update data
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || klineData.length === 0) return;

    const candleData: CandlestickData<Time>[] = klineData.map((d) => ({
      time: d.date as Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const volumeData: HistogramData<Time>[] = klineData.map((d) => ({
      time: d.date as Time,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(239, 83, 80, 0.3)' : 'rgba(38, 166, 154, 0.3)',
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);

    // MA lines
    maSeriesRef.current.forEach((s) => s.remove());
    maSeriesRef.current = [];

    const maConfigs = [
      { key: 'ma5' as const, period: 5, color: '#2196f3' },
      { key: 'ma10' as const, period: 10, color: '#ff9800' },
      { key: 'ma20' as const, period: 20, color: '#9c27b0' },
    ];

    maConfigs.forEach((cfg) => {
      if (showMA[cfg.key] && chartRef.current) {
        const maData = calcMA(klineData, cfg.period);
        const lineSeries = chartRef.current.addSeries(LineSeries, {
          color: cfg.color,
          lineWidth: 1,
          title: `MA${cfg.period}`,
        });
        lineSeries.setData(maData);
        maSeriesRef.current.push(lineSeries as ISeriesApi<'Line'>);
      }
    });

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [klineData, showMA]);

  const isLoading = klineQuery.isLoading && !klineQuery.data;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: 24 }}>
      {/* Header */}
      <Row justify="space-between" align="middle">
        <Col>
          <Space align="baseline">
            <Typography.Title level={4} style={{ margin: 0 }}>
              {quote?.name || code}
            </Typography.Title>
            <Typography.Text type="secondary">{code}</Typography.Text>
            {quote && (
              <Tag color={quote.change_pct > 0 ? 'red' : quote.change_pct < 0 ? 'green' : 'default'}>
                {quote.change_pct > 0 ? '+' : ''}{quote.change_pct.toFixed(2)}%
              </Tag>
            )}
          </Space>
        </Col>
        <Col>
          <Space>
            <Select
              value={period}
              onChange={setPeriod}
              options={PERIOD_OPTIONS}
              style={{ width: 100 }}
            />
            <Checkbox
              checked={showMA.ma5}
              onChange={(e) => setShowMA((p) => ({ ...p, ma5: e.target.checked }))}
            >
              <span style={{ color: '#2196f3' }}>MA5</span>
            </Checkbox>
            <Checkbox
              checked={showMA.ma10}
              onChange={(e) => setShowMA((p) => ({ ...p, ma10: e.target.checked }))}
            >
              <span style={{ color: '#ff9800' }}>MA10</span>
            </Checkbox>
            <Checkbox
              checked={showMA.ma20}
              onChange={(e) => setShowMA((p) => ({ ...p, ma20: e.target.checked }))}
            >
              <span style={{ color: '#9c27b0' }}>MA20</span>
            </Checkbox>
          </Space>
        </Col>
      </Row>

      {/* Quote info */}
      {quote && (
        <Card size="small">
          <Row gutter={16}>
            <Col span={3}>
              <Statistic
                title="现价"
                value={quote.price}
                precision={2}
                valueStyle={{ color: quote.change_pct > 0 ? '#ef5350' : '#26a69a', fontSize: 24 }}
              />
            </Col>
            <Col span={3}>
              <Statistic title="涨跌额" value={quote.change} precision={2} />
            </Col>
            <Col span={3}>
              <Statistic title="涨跌幅" value={quote.change_pct} precision={2} suffix="%" />
            </Col>
            <Col span={3}>
              <Statistic title="开盘" value={quote.open} precision={2} />
            </Col>
            <Col span={3}>
              <Statistic title="最高" value={quote.high} precision={2} />
            </Col>
            <Col span={3}>
              <Statistic title="最低" value={quote.low} precision={2} />
            </Col>
            <Col span={3}>
              <Statistic title="昨收" value={quote.prev_close} precision={2} />
            </Col>
            <Col span={3}>
              <Statistic title="成交量" value={quote.volume} />
            </Col>
          </Row>
        </Card>
      )}

      {/* Chart */}
      <Spin spinning={isLoading}>
        <Card title="K线图" size="small">
          <div ref={chartContainerRef} />
        </Card>
        <Card title="成交量" size="small" style={{ marginTop: 8 }}>
          <div ref={volumeContainerRef} />
        </Card>
      </Spin>
    </Space>
  );
}
