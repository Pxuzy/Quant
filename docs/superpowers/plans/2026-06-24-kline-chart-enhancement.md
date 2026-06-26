# Kline Chart Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the stock K-line page so it has A-share red/green candlesticks and volume bars, drag/zoom navigation, period/range controls, and practical MA/BOLL/MACD/RSI indicators.

**Architecture:** Keep the existing `lightweight-charts` dependency and the `/stock/$code` page. Move market data loading through the existing API client, keep indicator math as small pure helpers, and configure the chart in one focused page update without introducing a new charting library.

**Tech Stack:** React 18, TypeScript, Ant Design, TanStack Router, `lightweight-charts` 5.2.0, existing `apps/web/src/features/market/api.ts`.

---

## File Structure

- Modify: `apps/web/src/features/market/api.ts`
  - Keep the `KLine` type.
  - Extend `marketQueryKeys.kline` and `fetchKline` so the range/count is represented cleanly by callers.
- Modify: `apps/web/src/pages/stock/StockPage.tsx`
  - Remove direct `fetch` and hard-coded API host.
  - Preserve current route and page layout.
  - Configure chart scroll/zoom, price scales, red/green colors, volume, MA, BOLL, MACD, RSI, toolbar controls, and tooltip.
- Verify only: `apps/web/src/shared/api/client.ts`
  - Confirm no code change is needed; `fetchKline` should keep using `apiRequest`.

## Acceptance Criteria

- `/stock/$code` shows red candlesticks for up days and green candlesticks for down days.
- Volume bars use the same red/green direction as their candle.
- Users can drag the chart horizontally and use wheel/pinch to zoom the time scale.
- The toolbar can switch `日线 / 周线 / 月线`.
- The toolbar can switch `1M / 3M / 6M / 1Y / 3Y / 全部`.
- Users can toggle overlays: `MA5`, `MA10`, `MA20`, `BOLL`.
- Users can switch the lower indicator between `成交量`, `MACD`, and `RSI`.
- Crosshair tooltip shows date, OHLC,涨跌幅, and volume.
- No paid or new charting dependency is introduced.
- A screenshot is saved under `outputs/` after browser verification.

---

### Task 1: Route K-line Fetching Through The Existing API Client

**Files:**
- Modify: `apps/web/src/features/market/api.ts`
- Modify: `apps/web/src/pages/stock/StockPage.tsx`

- [ ] **Step 1: Update the K-line query key and fetch helper**

Change `apps/web/src/features/market/api.ts` so `count` participates in the query key and `fetchKline` builds query params through `apiRequest`:

```typescript
export const marketQueryKeys = {
  all: ['market'] as const,
  quotes: (codes: string[]) => [...marketQueryKeys.all, 'quotes', ...codes] as const,
  index: () => [...marketQueryKeys.all, 'index'] as const,
  kline: (code: string, period: string, count: number) => [...marketQueryKeys.all, 'kline', code, period, count] as const,
  news: (keyword: string) => [...marketQueryKeys.all, 'news', keyword] as const,
  search: (keyword: string) => [...marketQueryKeys.all, 'search', keyword] as const,
};

export function fetchKline(
  code: string,
  period: string = 'day',
  count: number = 100,
  signal?: AbortSignal,
): Promise<KLine[]> {
  return apiRequest<KLine[]>(
    '/api/market/kline',
    { code, period, count },
    { signal },
  );
}
```

- [ ] **Step 2: Remove hard-coded API access from `StockPage.tsx`**

Replace the local `API` constant and raw `fetch` call with:

```typescript
import { fetchKline, type KLine } from '../../features/market/api';
```

and inside the load function:

```typescript
const data = await fetchKline(fullCode, period, count);
```

- [ ] **Step 3: Type-check the changed API boundary**

Run:

```powershell
cd apps\web
npm run type-check
```

Expected: any new error must not come from `apps/web/src/features/market/api.ts` or `apps/web/src/pages/stock/StockPage.tsx`. Existing unrelated errors in watchlist or legacy chart namespace may remain and should be reported separately.

---

### Task 2: Configure A-share K-line Colors, Dragging, Zooming, And Tooltip

**Files:**
- Modify: `apps/web/src/pages/stock/StockPage.tsx`

- [ ] **Step 1: Define stable color and period constants**

Add near the top of `StockPage.tsx`:

```typescript
const UP_COLOR = '#d9363e';
const DOWN_COLOR = '#009966';
const UP_VOLUME_COLOR = 'rgba(217, 54, 62, 0.38)';
const DOWN_VOLUME_COLOR = 'rgba(0, 153, 102, 0.38)';

const PERIOD_OPTIONS = [
  { label: '日线', value: 'day' },
  { label: '周线', value: 'week' },
  { label: '月线', value: 'month' },
] as const;

const RANGE_OPTIONS = ['1M', '3M', '6M', '1Y', '3Y', '全部'] as const;
type PeriodValue = (typeof PERIOD_OPTIONS)[number]['value'];
type RangeValue = (typeof RANGE_OPTIONS)[number];
```

- [ ] **Step 2: Extend the range count helper**

Use:

```typescript
function countFromRange(range: RangeValue): number {
  switch (range) {
    case '1M': return 22;
    case '3M': return 66;
    case '6M': return 132;
    case '1Y': return 250;
    case '3Y': return 750;
    case '全部': return 2000;
  }
}
```

- [ ] **Step 3: Configure chart interactions**

In `createChart`, use the existing chart options but ensure:

```typescript
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
timeScale: {
  timeVisible: false,
  secondsVisible: false,
  borderColor: '#e0e0e0',
  rightOffset: 8,
  barSpacing: 8,
  minBarSpacing: 3,
},
```

- [ ] **Step 4: Apply red/green candle and volume bars**

Set candlestick series colors:

```typescript
const candleSeries = chart.addSeries(CandlestickSeries, {
  upColor: UP_COLOR,
  downColor: DOWN_COLOR,
  borderUpColor: UP_COLOR,
  borderDownColor: DOWN_COLOR,
  wickUpColor: UP_COLOR,
  wickDownColor: DOWN_COLOR,
});
```

Set volume colors:

```typescript
volumeSeries.setData(data.map((d) => ({
  time: d.date as Time,
  value: d.volume,
  color: d.close >= d.open ? UP_VOLUME_COLOR : DOWN_VOLUME_COLOR,
} as HistogramData)));
```

- [ ] **Step 5: Improve tooltip content**

Tooltip should show at least:

```typescript
const pct = ((cd.close - cd.open) / cd.open) * 100;
tooltip.innerHTML = `
  <div><b>${cd.time}</b></div>
  <div>开 ${cd.open.toFixed(2)} 高 ${cd.high.toFixed(2)} 低 ${cd.low.toFixed(2)} 收 ${cd.close.toFixed(2)}</div>
  <div>涨跌 <span style="color:${pct >= 0 ? UP_COLOR : DOWN_COLOR}">${pct.toFixed(2)}%</span></div>
  <div>成交量 ${fmt(currentVolume)}</div>
`;
```

---

### Task 3: Add Practical Indicator Controls

**Files:**
- Modify: `apps/web/src/pages/stock/StockPage.tsx`

- [ ] **Step 1: Add indicator state**

Use minimal state:

```typescript
const [enabledOverlays, setEnabledOverlays] = useState<string[]>(['MA5', 'MA10', 'MA20']);
const [lowerIndicator, setLowerIndicator] = useState<'volume' | 'macd' | 'rsi'>('volume');
```

- [ ] **Step 2: Add toolbar controls**

Add an Ant Design segmented control for lower indicator:

```tsx
<Segmented
  value={lowerIndicator}
  onChange={(v) => setLowerIndicator(v as 'volume' | 'macd' | 'rsi')}
  options={[
    { label: '成交量', value: 'volume' },
    { label: 'MACD', value: 'macd' },
    { label: 'RSI', value: 'rsi' },
  ]}
/>
```

Add a compact checkbox group for overlays:

```tsx
<Checkbox.Group
  value={enabledOverlays}
  onChange={(values) => setEnabledOverlays(values.map(String))}
  options={['MA5', 'MA10', 'MA20', 'BOLL']}
/>
```

`Checkbox` must be imported from `antd`.

- [ ] **Step 3: Render MA and BOLL only when enabled**

Use the existing `calcMA` and `calcBOLL`, guarded by:

```typescript
if (enabledOverlays.includes('MA5') && data.length >= 5) {
  chart.addSeries(LineSeries, { color: '#f59f00', lineWidth: 1, priceLineVisible: false }).setData(calcMA(data, 5));
}
```

Repeat for `MA10`, `MA20`, and `BOLL`.

- [ ] **Step 4: Render only the selected lower indicator**

Keep one lower price scale and switch data by `lowerIndicator`:

```typescript
if (lowerIndicator === 'volume') {
  // render volume histogram
}

if (lowerIndicator === 'macd' && data.length > 26) {
  // render MACD histogram and two lines
}

if (lowerIndicator === 'rsi' && data.length > 14) {
  // render RSI line on the lower scale
}
```

- [ ] **Step 5: Make RSI safe for short data**

Update `calcRSI` so it returns an empty array when `data.length <= period`:

```typescript
function calcRSI(data: KlineItem[], period = 14): RSIValue[] {
  if (data.length <= period) return [];
  // existing calculation
}
```

---

### Task 4: Verify In Browser And Save Screenshot

**Files:**
- Verify: `apps/web/src/pages/stock/StockPage.tsx`
- Create: `outputs/kline-chart-enhancement.png`

- [ ] **Step 1: Start or reuse the local workbench**

Run from repo root:

```powershell
.\scripts\quant-dev.cmd status
.\scripts\quant-dev.cmd start-bg
```

If already running, do not kill unrelated processes.

- [ ] **Step 2: Open a stock page**

Use a known A-share code route:

```text
http://127.0.0.1:5175/stock/600519
```

If that route has no local data, use another known code from the stock pool.

- [ ] **Step 3: Manual interaction checks**

Check:

- Drag left/right moves the time window.
- Mouse wheel zooms the K-line time scale.
- `日线 / 周线 / 月线` refreshes data.
- `1M / 3M / 6M / 1Y / 3Y / 全部` changes visible history.
- `MA5 / MA10 / MA20 / BOLL` toggles overlays.
- `成交量 / MACD / RSI` switches the lower pane.
- Tooltip follows the crosshair and shows OHLC,涨跌幅,成交量.

- [ ] **Step 4: Save screenshot**

Save a screenshot to:

```text
outputs/kline-chart-enhancement.png
```

- [ ] **Step 5: Final verification commands**

Run:

```powershell
cd apps\web
npm run type-check
```

Expected: report whether it passes. If it fails only on pre-existing unrelated files, state the exact files and keep the K-line page free of new type errors.

---

## Skipped

- skipped: new charting dependency, add when `lightweight-charts` cannot support required interactions or indicators.
- skipped: full TradingView-style indicator editor, add when the research workflow needs custom indicator parameters.
- skipped: backend K-line API changes, add when period/range aggregation cannot be satisfied by the existing `/api/market/kline` contract.
- skipped: front-end test runner setup, add when the repository standardizes on Vitest or another React testing stack.
