import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from '@tanstack/react-router';
import { Button, Card, Checkbox, Divider, InputNumber, Popover, Segmented, Space, Spin, Typography } from 'antd';
import { ExpandOutlined, SettingOutlined } from '@ant-design/icons';

import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type IRange,
  type ISeriesApi,
  type LineData,
  type SeriesType,
  type Time,
  CrosshairMode,
  LineStyle,
} from 'lightweight-charts';
import { fetchKline, type KLine } from '../../features/market/api';
import {
  DOWN_COLOR,
  DOWN_VOLUME_COLOR,
  UP_COLOR,
  UP_VOLUME_COLOR,
  buildCandleData,
  buildVolumeData,
  calcBOLL,
  calcKDJ,
  calcMACD,
  calcMA,
  calcRSI,
  getKlineDirection,
  type BollSettings,
  type KDJSettings,
  type MACDSettings,
  type RSISettings,
} from './klineIndicators';

const LOWER_PANE_INDEX = 1;

const PERIOD_OPTIONS = [
  { label: '\u65e5\u7ebf', value: 'day' },
  { label: '\u5468\u7ebf', value: 'week' },
  { label: '\u6708\u7ebf', value: 'month' },
] as const;

const RANGE_OPTIONS = ['1M', '3M', '6M', '1Y', '3Y', '\u5168\u90e8'] as const;
const DEFAULT_MA_PERIODS = [5, 10, 20, 60] as const;
const MA_COLORS = ['#f59f00', '#1677ff', '#722ed1', '#a0d911'] as const;
const RSI_COLORS = ['#1677ff', '#fa8c16', '#722ed1'] as const;
const KDJ_COLORS = { k: '#1677ff', d: '#fa8c16', j: '#722ed1' } as const;
const DEFAULT_BOLL_SETTINGS: BollSettings = { period: 20, multiplier: 2 };
const DEFAULT_MACD_SETTINGS: MACDSettings = { fast: 12, slow: 26, signal: 9 };
const DEFAULT_RSI_PERIODS: RSISettings = [6, 12, 24];
const DEFAULT_KDJ_SETTINGS: KDJSettings = { period: 9, k: 3, d: 3 };

type PeriodValue = (typeof PERIOD_OPTIONS)[number]['value'];
type RangeValue = (typeof RANGE_OPTIONS)[number];
type OverlayValue = `MA${number}` | 'BOLL';
type LowerIndicator = 'volume' | 'macd' | 'rsi' | 'kdj';
type AnySeries = ISeriesApi<SeriesType, Time>;

function detectPrefix(code: string): string {
  if (code.startsWith('sh') || code.startsWith('sz') || code.startsWith('bj')) return '';
  if (code.startsWith('6') || code.startsWith('68')) return 'sh';
  return 'sz';
}

function fmt(v: number): string {
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '\u4ebf';
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '\u4e07';
  return v.toFixed(0);
}

function countFromRange(range: RangeValue): number {
  switch (range) {
    case '1M': return 22;
    case '3M': return 66;
    case '6M': return 132;
    case '1Y': return 250;
    case '3Y': return 750;
    case '\u5168\u90e8': return 2000;
  }
}

type StockKlineChartProps = {
  code: string;
  title?: string;
  embedded?: boolean;
  minHeight?: number;
};

export function StockKlineChart({ code, title, embedded = false, minHeight = 520 }: StockKlineChartProps) {
  const [period, setPeriod] = useState<PeriodValue>('day');
  const [range, setRange] = useState<RangeValue>('6M');
  const [loading, setLoading] = useState(true);
  const [klineData, setKlineData] = useState<KLine[]>([]);
  const [enabledOverlays, setEnabledOverlays] = useState<OverlayValue[]>(
    DEFAULT_MA_PERIODS.map((item) => `MA${item}` as OverlayValue),
  );
  const [lowerIndicator, setLowerIndicator] = useState<LowerIndicator>('volume');
  const [maPeriods, setMaPeriods] = useState<number[]>([...DEFAULT_MA_PERIODS]);
  const [bollSettings, setBollSettings] = useState<BollSettings>(DEFAULT_BOLL_SETTINGS);
  const [macdSettings, setMacdSettings] = useState<MACDSettings>(DEFAULT_MACD_SETTINGS);
  const [rsiPeriods, setRsiPeriods] = useState<RSISettings>(DEFAULT_RSI_PERIODS);
  const [kdjSettings, setKdjSettings] = useState<KDJSettings>(DEFAULT_KDJ_SETTINGS);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi>();
  const requestIdRef = useRef(0);
  const shouldFitContentRef = useRef(true);

  const loadKline = useCallback(async (signal?: AbortSignal) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    try {
      const count = countFromRange(range);
      const fullCode = detectPrefix(code) + code;
      const data = await fetchKline(fullCode, period, count, signal);
      if (signal?.aborted || requestId !== requestIdRef.current) return;
      shouldFitContentRef.current = true;
      setKlineData(data);
    } catch (e) {
      if (signal?.aborted) return;
      console.error('Kline fetch failed', e);
    } finally {
      if (!signal?.aborted && requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [code, period, range]);

  const renderMainIndicators = useCallback((chart: IChartApi, data: KLine[]) => {
    maPeriods.forEach((maPeriod, index) => {
      const key = `MA${maPeriod}` as OverlayValue;
      if (enabledOverlays.includes(key) && data.length >= maPeriod) {
        chart.addSeries(LineSeries, {
          color: MA_COLORS[index % MA_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          title: key,
        }).setData(calcMA(data, maPeriod));
      }
    });

    if (!enabledOverlays.includes('BOLL') || data.length < bollSettings.period) return;

    const boll = calcBOLL(data, bollSettings);
    chart.addSeries(LineSeries, { color: '#13c2c2', lineWidth: 1, priceLineVisible: false, title: 'BOLL U' })
      .setData(boll.map((item) => ({ time: item.time, value: item.upper })));
    chart.addSeries(LineSeries, {
      color: '#13c2c2',
      lineWidth: 1,
      priceLineVisible: false,
      lineStyle: LineStyle.Dotted,
      title: 'BOLL',
    }).setData(boll.map((item) => ({ time: item.time, value: item.mid })));
    chart.addSeries(LineSeries, { color: '#13c2c2', lineWidth: 1, priceLineVisible: false, title: 'BOLL L' })
      .setData(boll.map((item) => ({ time: item.time, value: item.lower })));
  }, [bollSettings, enabledOverlays, maPeriods]);

  const renderLowerIndicator = useCallback((chart: IChartApi, data: KLine[]) => {
    if (lowerIndicator === 'volume') {
      chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: 'right',
        priceLineVisible: false,
        lastValueVisible: false,
      }, LOWER_PANE_INDEX).setData(buildVolumeData(data));
      return;
    }

    if (lowerIndicator === 'macd' && data.length > macdSettings.slow) {
      const macd = calcMACD(data, macdSettings);
      chart.addSeries(LineSeries, {
        color: '#1677ff',
        lineWidth: 1,
        priceScaleId: 'right',
        title: 'DIF',
      }, LOWER_PANE_INDEX).setData(macd.map((item) => ({ time: item.time, value: item.macd } as LineData)));
      chart.addSeries(LineSeries, {
        color: '#fa8c16',
        lineWidth: 1,
        priceScaleId: 'right',
        title: 'DEA',
      }, LOWER_PANE_INDEX).setData(macd.map((item) => ({ time: item.time, value: item.signal } as LineData)));
      chart.addSeries(HistogramSeries, {
        priceScaleId: 'right',
        priceFormat: { type: 'price', precision: 4, minMove: 0.0001 },
        priceLineVisible: false,
        lastValueVisible: false,
      }, LOWER_PANE_INDEX).setData(macd.map((item) => ({
        time: item.time,
        value: item.histogram,
        color: item.histogram >= 0 ? UP_VOLUME_COLOR : DOWN_VOLUME_COLOR,
      } as HistogramData)));
      return;
    }

    if (lowerIndicator === 'rsi') {
      const rsiSets = calcRSI(data, rsiPeriods);
      rsiSets.forEach((set, index) => {
        if (!set.values.length) return;
        chart.addSeries(LineSeries, {
          color: RSI_COLORS[index % RSI_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          priceScaleId: 'right',
          title: `RSI${set.period}`,
        }, LOWER_PANE_INDEX).setData(set.values.map((item) => ({ time: item.time, value: item.value })));
      });
      const referenceData = rsiSets.find((set) => set.values.length)?.values ?? [];
      if (!referenceData.length) return;
      chart.addSeries(LineSeries, {
        color: '#bfbfbf',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        priceScaleId: 'right',
      }, LOWER_PANE_INDEX).setData(referenceData.map((item) => ({ time: item.time, value: 70 })));
      chart.addSeries(LineSeries, {
        color: '#bfbfbf',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        priceScaleId: 'right',
      }, LOWER_PANE_INDEX).setData(referenceData.map((item) => ({ time: item.time, value: 30 })));
      return;
    }

    const kdj = calcKDJ(data, kdjSettings);
    if (!kdj.length) return;

    chart.addSeries(LineSeries, {
      color: KDJ_COLORS.k,
      lineWidth: 1,
      priceLineVisible: false,
      priceScaleId: 'right',
      title: 'K',
    }, LOWER_PANE_INDEX).setData(kdj.map((item) => ({ time: item.time, value: item.k })));
    chart.addSeries(LineSeries, {
      color: KDJ_COLORS.d,
      lineWidth: 1,
      priceLineVisible: false,
      priceScaleId: 'right',
      title: 'D',
    }, LOWER_PANE_INDEX).setData(kdj.map((item) => ({ time: item.time, value: item.d })));
    chart.addSeries(LineSeries, {
      color: KDJ_COLORS.j,
      lineWidth: 1,
      priceLineVisible: false,
      priceScaleId: 'right',
      title: 'J',
    }, LOWER_PANE_INDEX).setData(kdj.map((item) => ({ time: item.time, value: item.j })));
  }, [kdjSettings, lowerIndicator, macdSettings, rsiPeriods]);

  const attachTooltip = useCallback((
    chart: IChartApi,
    container: HTMLDivElement,
    candleSeries: AnySeries,
    data: KLine[],
    width: number,
    height: number,
  ) => {
    const tooltip = document.createElement('div');
    tooltip.style.cssText = 'position:absolute;background:#fff;border:1px solid #ddd;border-radius:4px;padding:8px 10px;font-size:12px;line-height:1.6;pointer-events:none;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,0.1);display:none;';
    container.appendChild(tooltip);

    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !param.time) {
        tooltip.style.display = 'none';
        return;
      }
      const cd = param.seriesData.get(candleSeries) as CandlestickData | undefined;
      if (!cd) {
        tooltip.style.display = 'none';
        return;
      }

      const currentIndex = data.findIndex((item) => item.date === String(cd.time));
      const current = currentIndex >= 0 ? data[currentIndex] : undefined;
      const previous = currentIndex > 0 ? data[currentIndex - 1] : undefined;
      const change = current && previous ? current.close - previous.close : cd.close - cd.open;
      const base = previous?.close ?? cd.open;
      const pct = base === 0 ? 0 : (change / base) * 100;
      const direction = current ? getKlineDirection(current, previous) : cd.close >= cd.open ? 'up' : 'down';
      const color = direction === 'up' ? UP_COLOR : DOWN_COLOR;

      tooltip.style.display = 'block';
      tooltip.style.left = `${Math.min(param.point.x + 12, Math.max(0, width - 240))}px`;
      tooltip.style.top = `${Math.max(8, Math.min(param.point.y - 90, height - 126))}px`;
      tooltip.innerHTML = `
        <div><b>${cd.time}</b></div>
        <div>\u5f00 ${cd.open.toFixed(2)} \u9ad8 ${cd.high.toFixed(2)} \u4f4e ${cd.low.toFixed(2)} \u6536 ${cd.close.toFixed(2)}</div>
        <div>\u6da8\u8dcc\u989d <span style="color:${color}">${change.toFixed(2)}</span> \u6da8\u8dcc\u5e45 <span style="color:${color}">${pct.toFixed(2)}%</span></div>
        <div>\u6210\u4ea4\u91cf ${fmt(current?.volume ?? 0)}</div>
      `;
    });
  }, []);

  const renderChart = useCallback((data: KLine[]) => {
    if (!chartRef.current) return;

    const container = chartRef.current;
    const previousRange: IRange<Time> | null = chartApiRef.current?.timeScale().getVisibleRange() ?? null;
    const w = container.clientWidth;
    const h = container.clientHeight || 420;

    chartApiRef.current?.remove();
    container.innerHTML = '';
    chartApiRef.current = undefined;

    if (!data.length) return;

    const chart = createChart(container, {
      width: w,
      height: h,
      layout: { background: { color: '#ffffff' }, textColor: '#555', attributionLogo: false },
      grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
      timeScale: {
        timeVisible: false,
        secondsVisible: false,
        borderColor: '#e0e0e0',
        rightOffset: 8,
        barSpacing: 8,
        minBarSpacing: 3,
      },
      rightPriceScale: { borderColor: '#e0e0e0', scaleMargins: { top: 0.05, bottom: 0.08 } },
      crosshair: { mode: CrosshairMode.Normal },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });
    chartApiRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderUpColor: UP_COLOR,
      borderDownColor: DOWN_COLOR,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
    });
    candleSeries.setData(buildCandleData(data));

    const lowerPane = chart.addPane();
    chart.panes()[0]?.setStretchFactor(0.74);
    lowerPane.setStretchFactor(0.26);
    chart.priceScale('right', LOWER_PANE_INDEX).applyOptions({ borderColor: '#e0e0e0' });

    renderMainIndicators(chart, data);
    renderLowerIndicator(chart, data);

    if (!shouldFitContentRef.current && previousRange) {
      try {
        chart.timeScale().setVisibleRange(previousRange);
      } catch {
        chart.timeScale().fitContent();
      }
    } else {
      chart.timeScale().fitContent();
    }
    shouldFitContentRef.current = false;

    attachTooltip(chart, container, candleSeries, data, w, h);
  }, [attachTooltip, renderLowerIndicator, renderMainIndicators]);

  useEffect(() => {
    const controller = new AbortController();
    void loadKline(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadKline]);

  useEffect(() => {
    renderChart(klineData);
  }, [klineData, renderChart]);

  useEffect(() => () => {
    chartApiRef.current?.remove();
    chartApiRef.current = undefined;
  }, []);

  // Resize
  useEffect(() => {
    const onResize = () => {
      if (!chartRef.current || !chartApiRef.current) return;
      chartApiRef.current.applyOptions({ width: chartRef.current.clientWidth });
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const fitContent = useCallback(() => {
    shouldFitContentRef.current = true;
    chartApiRef.current?.timeScale().fitContent();
  }, []);

  const updateMaPeriod = useCallback((index: number, value: number | null) => {
    if (!value) return;
    const nextValue = Math.max(1, Math.round(value));
    const previousKey = `MA${maPeriods[index]}` as OverlayValue;
    const nextKey = `MA${nextValue}` as OverlayValue;
    setMaPeriods((prev) => prev.map((item, itemIndex) => (itemIndex === index ? nextValue : item)));
    setEnabledOverlays((prev) => prev.map((item) => (item === previousKey ? nextKey : item)));
  }, [maPeriods]);

  const overlayOptions = [
    ...maPeriods.map((item) => ({ label: `MA${item}`, value: `MA${item}` as OverlayValue })),
    { label: 'BOLL', value: 'BOLL' as OverlayValue },
  ];

  const settingsContent = (
    <div style={{ width: 292 }}>
      <Typography.Text strong>{'\u4e3b\u56fe\u6307\u6807'}</Typography.Text>
      <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 8 }}>
        <Space size={8} wrap>
          <Typography.Text type="secondary" style={{ width: 42 }}>MA</Typography.Text>
          {maPeriods.map((item, index) => (
            <InputNumber
              key={index}
              min={1}
              max={250}
              size="small"
              value={item}
              onChange={(value) => updateMaPeriod(index, value)}
              style={{ width: 56 }}
            />
          ))}
        </Space>
        <Space size={8}>
          <Typography.Text type="secondary" style={{ width: 42 }}>BOLL</Typography.Text>
          <InputNumber
            min={1}
            max={250}
            size="small"
            value={bollSettings.period}
            onChange={(value) => value && setBollSettings((prev) => ({ ...prev, period: Math.round(value) }))}
            style={{ width: 70 }}
          />
          <InputNumber
            min={0.1}
            max={5}
            step={0.1}
            size="small"
            value={bollSettings.multiplier}
            onChange={(value) => value && setBollSettings((prev) => ({ ...prev, multiplier: value }))}
            style={{ width: 70 }}
          />
        </Space>
      </Space>
      <Divider style={{ margin: '12px 0' }} />
      <Typography.Text strong>{'\u526f\u56fe\u6307\u6807'}</Typography.Text>
      <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 8 }}>
        <Space size={8}>
          <Typography.Text type="secondary" style={{ width: 48 }}>MACD</Typography.Text>
          <InputNumber min={1} max={250} size="small" value={macdSettings.fast} onChange={(value) => value && setMacdSettings((prev) => ({ ...prev, fast: Math.round(value) }))} style={{ width: 58 }} />
          <InputNumber min={1} max={250} size="small" value={macdSettings.slow} onChange={(value) => value && setMacdSettings((prev) => ({ ...prev, slow: Math.round(value) }))} style={{ width: 58 }} />
          <InputNumber min={1} max={250} size="small" value={macdSettings.signal} onChange={(value) => value && setMacdSettings((prev) => ({ ...prev, signal: Math.round(value) }))} style={{ width: 58 }} />
        </Space>
        <Space size={8}>
          <Typography.Text type="secondary" style={{ width: 48 }}>RSI</Typography.Text>
          {rsiPeriods.map((item, index) => (
            <InputNumber
              key={index}
              min={1}
              max={250}
              size="small"
              value={item}
              onChange={(value) => value && setRsiPeriods((prev) => prev.map((periodItem, periodIndex) => (periodIndex === index ? Math.round(value) : periodItem)))}
              style={{ width: 58 }}
            />
          ))}
        </Space>
        <Space size={8}>
          <Typography.Text type="secondary" style={{ width: 48 }}>KDJ</Typography.Text>
          <InputNumber min={1} max={250} size="small" value={kdjSettings.period} onChange={(value) => value && setKdjSettings((prev) => ({ ...prev, period: Math.round(value) }))} style={{ width: 58 }} />
          <InputNumber min={1} max={20} size="small" value={kdjSettings.k} onChange={(value) => value && setKdjSettings((prev) => ({ ...prev, k: Math.round(value) }))} style={{ width: 58 }} />
          <InputNumber min={1} max={20} size="small" value={kdjSettings.d} onChange={(value) => value && setKdjSettings((prev) => ({ ...prev, d: Math.round(value) }))} style={{ width: 58 }} />
        </Space>
      </Space>
    </div>
  );

  const chartControls = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: embedded ? 0 : 12, flexWrap: 'wrap' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>{title ?? code.toUpperCase()}</Typography.Title>
      <Segmented
        value={period}
        onChange={(v) => setPeriod(v as PeriodValue)}
        options={[...PERIOD_OPTIONS]}
      />
      <Segmented
        value={range}
        onChange={(v) => setRange(v as RangeValue)}
        options={[...RANGE_OPTIONS]}
      />
      <Segmented
        value={lowerIndicator}
        onChange={(v) => setLowerIndicator(v as LowerIndicator)}
        options={[
          { label: '\u6210\u4ea4\u91cf', value: 'volume' },
          { label: 'MACD', value: 'macd' },
          { label: 'RSI', value: 'rsi' },
          { label: 'KDJ', value: 'kdj' },
        ]}
      />
      <Space size={6} wrap>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>{'\u4e3b\u56fe\u6307\u6807'}</Typography.Text>
        <Checkbox.Group
          value={enabledOverlays}
          onChange={(values) => setEnabledOverlays(values as OverlayValue[])}
          options={overlayOptions}
        />
      </Space>
      <Button icon={<ExpandOutlined />} size="small" title={'\u5168\u56fe'} onClick={fitContent} />
      <Popover content={settingsContent} trigger="click" placement="bottomRight">
        <Button icon={<SettingOutlined />} size="small" title={'\u8bbe\u7f6e'} />
      </Popover>
      {loading && <Spin size="small" />}
    </div>
  );

  const chartNode = (
    <div
      ref={chartRef}
      onDoubleClick={fitContent}
      style={{ width: '100%', height: '100%', minHeight, position: 'relative' }}
    />
  );

  if (embedded) {
    return (
      <div className="stock-kline-chart stock-kline-chart-embedded" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {chartControls}
        <div style={{ minHeight, height: minHeight }}>{chartNode}</div>
      </div>
    );
  }

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {chartControls}
      <Card styles={{ body: { padding: 0, height: '100%', minHeight: 0 } }} style={{ flex: 1, minHeight }}>
        {chartNode}
      </Card>
    </div>
  );
}

export function StockPage() {
  const { code } = useParams({ from: '/stock/$code' });

  return <StockKlineChart code={code} />;
}
