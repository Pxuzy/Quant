import type { CandlestickData, HistogramData, LineData, Time } from 'lightweight-charts';
import type { KLine } from '../../features/market/api';

export const UP_COLOR = '#d9363e';
export const DOWN_COLOR = '#009966';
export const UP_VOLUME_COLOR = 'rgba(217, 54, 62, 0.38)';
export const DOWN_VOLUME_COLOR = 'rgba(0, 153, 102, 0.38)';

export type KlineItem = KLine;
export type KlineDirection = 'up' | 'down';
export type MACDSettings = { fast: number; slow: number; signal: number };
export type RSISettings = number[];
export type BollSettings = { period: number; multiplier: number };
export type KDJSettings = { period: number; k: number; d: number };
export type MACDValue = { time: Time; macd: number; signal: number; histogram: number };
export type RSIValue = { time: Time; value: number };
export type RSISet = { period: number; values: RSIValue[] };
export type BollValue = { time: Time; upper: number; mid: number; lower: number };
export type KDJValue = { time: Time; k: number; d: number; j: number };

const round = (value: number, digits = 2): number => Number(value.toFixed(digits));

export function getKlineDirection(current: KlineItem, previous?: KlineItem): KlineDirection {
  if (previous) return current.close >= previous.close ? 'up' : 'down';
  return current.close >= current.open ? 'up' : 'down';
}

export function getKlineColors(current: KlineItem, previous?: KlineItem): { candle: string; volume: string } {
  const isUp = getKlineDirection(current, previous) === 'up';
  return {
    candle: isUp ? UP_COLOR : DOWN_COLOR,
    volume: isUp ? UP_VOLUME_COLOR : DOWN_VOLUME_COLOR,
  };
}

export function buildCandleData(data: KlineItem[]): CandlestickData[] {
  return data.map((item, index) => {
    const color = getKlineColors(item, data[index - 1]).candle;
    return {
      time: item.date as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
      color,
      borderColor: color,
      wickColor: color,
    };
  });
}

export function buildVolumeData(data: KlineItem[]): HistogramData[] {
  return data.map((item, index) => ({
    time: item.date as Time,
    value: item.volume,
    color: getKlineColors(item, data[index - 1]).volume,
  }));
}

export function calcMA(data: KlineItem[], period: number): LineData[] {
  return data.flatMap((item, index) => {
    if (index < period - 1) return [];
    const slice = data.slice(index - period + 1, index + 1);
    const avg = slice.reduce((sum, value) => sum + value.close, 0) / period;
    return { time: item.date as Time, value: round(avg) };
  });
}

export function calcEMA(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [];
  let ema = values[0] ?? 0;
  for (let i = 0; i < values.length; i += 1) {
    ema = i === 0 ? values[i] : values[i] * k + ema * (1 - k);
    result.push(round(ema, 4));
  }
  return result;
}

export function calcMACD(data: KlineItem[], settings: MACDSettings = { fast: 12, slow: 26, signal: 9 }): MACDValue[] {
  const closes = data.map((item) => item.close);
  const fast = calcEMA(closes, settings.fast);
  const slow = calcEMA(closes, settings.slow);
  const diffs = fast.map((value, index) => value - slow[index]);
  const signal = calcEMA(diffs, settings.signal);
  return data.map((item, index) => ({
    time: item.date as Time,
    macd: round(diffs[index], 4),
    signal: round(signal[index], 4),
    histogram: round((diffs[index] - signal[index]) * 2, 4),
  }));
}

export function calcRSI(data: KlineItem[], periods: RSISettings = [6, 12, 24]): RSISet[] {
  return periods.map((period) => ({
    period,
    values: calcSingleRSI(data, period),
  }));
}

export function calcSingleRSI(data: KlineItem[], period: number): RSIValue[] {
  if (data.length <= period) return [];

  const changes: number[] = [];
  for (let i = 1; i < data.length; i += 1) {
    changes.push(data[i].close - data[i - 1].close);
  }

  const gains = changes.map((value) => (value > 0 ? value : 0));
  const losses = changes.map((value) => (value < 0 ? -value : 0));
  let avgGain = gains.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  const result: RSIValue[] = [];

  for (let i = period; i < data.length; i += 1) {
    if (i > period) {
      avgGain = (avgGain * (period - 1) + gains[i - 1]) / period;
      avgLoss = (avgLoss * (period - 1) + losses[i - 1]) / period;
    }
    const value = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    result.push({ time: data[i].date as Time, value: round(value) });
  }

  return result;
}

export function calcBOLL(data: KlineItem[], settings: BollSettings = { period: 20, multiplier: 2 }): BollValue[] {
  return data.flatMap((item, index) => {
    if (index < settings.period - 1) return [];
    const slice = data.slice(index - settings.period + 1, index + 1);
    const mid = slice.reduce((sum, value) => sum + value.close, 0) / settings.period;
    const variance = slice.reduce((sum, value) => sum + (value.close - mid) ** 2, 0) / settings.period;
    const std = Math.sqrt(variance);
    return {
      time: item.date as Time,
      upper: round(mid + settings.multiplier * std),
      mid: round(mid),
      lower: round(mid - settings.multiplier * std),
    };
  });
}

export function calcKDJ(data: KlineItem[], settings: KDJSettings = { period: 9, k: 3, d: 3 }): KDJValue[] {
  let kValue = 50;
  let dValue = 50;

  return data.flatMap((item, index) => {
    if (index < settings.period - 1) return [];
    const slice = data.slice(index - settings.period + 1, index + 1);
    const high = Math.max(...slice.map((value) => value.high));
    const low = Math.min(...slice.map((value) => value.low));
    const rsv = high === low ? 50 : ((item.close - low) / (high - low)) * 100;
    kValue = ((settings.k - 1) * kValue + rsv) / settings.k;
    dValue = ((settings.d - 1) * dValue + kValue) / settings.d;
    return {
      time: item.date as Time,
      k: round(kValue),
      d: round(dValue),
      j: round(3 * kValue - 2 * dValue),
    };
  });
}
