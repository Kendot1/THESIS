import assert from 'node:assert/strict';
import test from 'node:test';
import { withModelCapability } from './model-quality.ts';

const capability = { evaluation_source: 'historical_holdout',
  success_definition: 'absolute_percentage_error_at_most_tolerance', prediction_success: .74 };
const snapshot = { modelRunId: 'evaluated', metrics: capability };

test('uses measured capability for matching legacy model only', () => {
  assert.equal(withModelCapability({ modelRunId: 'evaluated', metrics: null }, snapshot).modelMetrics, capability);
  assert.equal(withModelCapability({ modelRunId: 'different', metrics: null }, snapshot).modelMetrics, null);
  assert.equal(withModelCapability(null, snapshot), null);
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
