import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeNewsResponse } from '../../../../../tmp/marketNews.mjs';

test('normalizes paginated news responses to item arrays', () => {
  const item = {
    title: 'A',
    url: 'https://example.test/a',
    summary: '',
    source: 'source',
    created_at: '2026-06-24',
  };

  assert.deepEqual(normalizeNewsResponse([item]), [item]);
  assert.deepEqual(normalizeNewsResponse({ items: [item] }), [item]);
  assert.deepEqual(normalizeNewsResponse({ data: [item] }), [item]);
  assert.deepEqual(normalizeNewsResponse({ results: [item] }), [item]);
  assert.deepEqual(normalizeNewsResponse({}), []);
});
