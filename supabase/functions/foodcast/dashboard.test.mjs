import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyDashboardSummary } from './dashboard.ts';

test('successful empty dashboard summary remains available and empty', () => {
  assert.deepEqual(classifyDashboardSummary({ rows: [] }, null), {
    kind: 'available', rows: [],
  });
});

test('successful legacy-required summary remains distinct from unavailable', () => {
  assert.deepEqual(classifyDashboardSummary({ rows: [], requires_legacy: true }, null), {
    kind: 'legacy_required',
  });
});

test('summary transport failure is unavailable, not a reason to use legacy reads', () => {
  assert.deepEqual(classifyDashboardSummary(null, new Error('timeout')), {
    kind: 'unavailable',
  });
});

test('malformed summary response is unavailable rather than authoritative empty', () => {
  assert.deepEqual(classifyDashboardSummary({ rows: null }, null), {
    kind: 'unavailable',
  });
});
