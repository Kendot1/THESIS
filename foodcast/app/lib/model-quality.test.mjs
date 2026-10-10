import assert from 'node:assert/strict';
import test from 'node:test';
import { withModelCapability } from './model-quality.ts';
import { formatNewsPublicationDate } from './data.ts';

const capability = { evaluation_source: 'chronological_validation',
  success_definition: 'absolute_percentage_error_at_most_tolerance', prediction_success: .74 };
const snapshot = { modelRunId: 'evaluated', metrics: capability };

test('formats only source-verified news publication dates', () => {
  assert.equal(formatNewsPublicationDate(null, '2025-07-22', 'date'), 'Jul 22, 2025');
  assert.equal(formatNewsPublicationDate('2025-07-22T16:40:00+08:00', '2025-07-22', 'timestamp'), 'Jul 22, 2025');
  assert.equal(formatNewsPublicationDate('2026-10-03T10:00:00Z', null, 'unknown'), 'Publication date unavailable');
  assert.equal(formatNewsPublicationDate(null, null, 'unknown', 'https://www.abs-cbn.com/news/business/2026/10/3/sample-article'), 'Oct 3, 2026');
  assert.equal(formatNewsPublicationDate(null, null, 'unknown', 'https://example.com/news/2026/2/30/sample'), 'Publication date unavailable');
  assert.equal(formatNewsPublicationDate('invalid', null, 'timestamp'), 'Publication date unavailable');
});

test('uses measured capability for matching legacy model only', () => {
  assert.deepEqual(withModelCapability({ modelRunId: 'evaluated', metrics: null }, snapshot).modelMetrics,
    { ...capability, product_metrics: {} });
  assert.equal(withModelCapability({ modelRunId: 'different', metrics: null }, snapshot).modelMetrics, null);
  assert.equal(withModelCapability(null, snapshot), null);
});

test('holdout-only summaries cannot bootstrap confidence or model capability', () => {
  const heldout = { ...capability, evaluation_source: 'historical_holdout' };
  const result = withModelCapability({ modelRunId: 'evaluated', metrics: null },
    { modelRunId: 'evaluated', metrics: heldout });
  assert.equal(result.modelMetrics, null);
});

test('keeps model capability separate from recent realized forecasts', () => {
  const realized = { ...capability, evaluation_source: 'realized_vintages', prediction_success: 1 };
  const result = withModelCapability({ modelRunId: 'evaluated', metrics: realized }, snapshot);
  assert.equal(result.metrics, realized);
  assert.equal(result.modelMetrics.prediction_success, .74);
});

test('prefers newly published evaluation over bootstrap', () => {
  const current = { ...capability, prediction_success: .8 };
  assert.equal(withModelCapability({ modelRunId: 'new', modelMetrics: current }, snapshot).modelMetrics, current);
});
