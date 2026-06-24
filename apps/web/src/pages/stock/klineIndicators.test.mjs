import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  buildCandleData,
  buildVolumeData,
  calcKDJ,
  calcMA,
  getKlineDirection,
} from '../../../../../tmp/klineIndicators.mjs';

const sample = [
  { date: '2026-01-01', open: 10, high: 11, low: 9, close: 10, volume: 100 },
  { date: '2026-01-02', open: 11, high: 12, low: 10, close: 10.5, volume: 120 },
  { date: '2026-01-03', open: 12, high: 13, low: 10, close: 10.2, volume: 130 },
  { date: '2026-01-04', open: 10, high: 11, low: 9, close: 10.2, volume: 140 },
];

describe('kline indicator helpers', () => {
  it('uses previous close for candle and volume direction', () => {
    assert.equal(getKlineDirection(sample[0]), 'up');
    assert.equal(getKlineDirection(sample[1], sample[0]), 'up');
    assert.equal(getKlineDirection(sample[2], sample[1]), 'down');
    assert.equal(getKlineDirection(sample[3], sample[2]), 'up');

    assert.deepEqual(
      buildCandleData(sample).map((item) => item.color),
      ['#d9363e', '#d9363e', '#009966', '#d9363e'],
    );
    assert.deepEqual(
      buildVolumeData(sample).map((item) => item.color),
      [
        'rgba(217, 54, 62, 0.38)',
        'rgba(217, 54, 62, 0.38)',
        'rgba(0, 153, 102, 0.38)',
        'rgba(217, 54, 62, 0.38)',
      ],
    );
  });

  it('waits for a full MA window before returning moving average points', () => {
    assert.deepEqual(calcMA(sample, 3), [
      { time: '2026-01-03', value: 10.23 },
      { time: '2026-01-04', value: 10.3 },
    ]);
  });

  it('calculates configurable KDJ values after the first full window', () => {
    const kdj = calcKDJ(sample, { period: 3, k: 3, d: 3 });

    assert.deepEqual(kdj, [
      { time: '2026-01-03', k: 43.33, d: 47.78, j: 34.44 },
      { time: '2026-01-04', k: 38.89, d: 44.81, j: 27.04 },
    ]);
  });
});
