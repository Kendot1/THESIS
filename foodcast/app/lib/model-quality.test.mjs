import assert from 'node:assert/strict';
import test from 'node:test';
import { withModelCapability } from './model-quality.ts';
import { verifiedRangeHitRate, verifiedLongRangeHitRate, verifiedCoverageConfidenceInterval, formatNewsPublicationDate } from './data.ts';

const capability = { evaluation_source: 'historical_holdout',
  success_definition: 'absolute_percentage_error_at_most_tolerance', prediction_success: .74 };
const snapshot = { modelRunId: 'evaluated', metrics: capability };

test('formats only source-verified news publication dates', () => {
  assert.equal(formatNewsPublicationDate(null, '2025-07-22', 'date'), 'Jul 22, 2025');
  assert.equal(formatNewsPublicationDate('2025-07-22T16:40:00+08:00', '2025-07-22', 'timestamp'), 'Jul 22, 2025');
  assert.equal(formatNewsPublicationDate('2026-10-03T10:00:00Z', null, 'unknown'), 'Publication date unavailable');
  assert.equal(formatNewsPublicationDate('invalid', null, 'timestamp'), 'Publication date unavailable');
});

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

test('range hit rate requires a measured 80% interval and enough outcomes', () => {
  assert.equal(verifiedRangeHitRate({ evaluation_source: 'historical_holdout', interval_level: .8, interval_coverage: .823,
    sample_count: 25889 }), .823);
  assert.equal(verifiedRangeHitRate({ evaluation_source: 'realized_vintages', interval_level: .8, interval_coverage: .5,
    sample_count: 19 }, 20), null);
  assert.equal(verifiedRangeHitRate({ evaluation_source: 'historical_holdout', interval_level: null, interval_coverage: .5,
    sample_count: 200 }), null);
  assert.equal(verifiedRangeHitRate({ evaluation_source: 'historical_holdout', interval_level: .9, interval_coverage: .91,
    sample_count: 200 }), null);
  assert.equal(verifiedRangeHitRate({ evaluation_source: 'unverified', interval_level: .8,
    interval_coverage: .99, sample_count: 200 }), null);
});

const longHistory = {
  evaluation_source: 'realized_vintages', interval_level: .8, interval_coverage: .75,
  covered_count: 15, sample_count: 20, effective_sample_count: 12,
  coverage_uncertainty_method: 'positive_serial_wilson_7d', coverage_uncertainty_approximate: true,
  // Synthetic approved fixture; current backend deliberately returns false.
  coverage_uncertainty_validated: true,
  sample_basis: 'unique_actual_dates',
  horizon_min_days: 15, horizon_max_days: 30, horizon_basis: 'philippine_publication_date',
  observed_min_lead_days: 15, observed_max_lead_days: 27,
};

test('long-range badge accepts only verified comparable lead-time history', () => {
  assert.equal(verifiedLongRangeHitRate(longHistory), .75);
  for (const changes of [
    { horizon_min_days: 1 }, { horizon_basis: undefined }, { sample_basis: undefined },
    { observed_min_lead_days: 14 }, { observed_max_lead_days: 31 },
    { observed_min_lead_days: 28, observed_max_lead_days: 27 },
    { sample_count: 19 }, { evaluation_source: 'historical_holdout' },
    { interval_level: .9 }, { observed_min_lead_days: undefined },
  ]) assert.equal(verifiedLongRangeHitRate({ ...longHistory, ...changes }), null);
});

test('confidence interval uses exact counts and rejects inconsistent evidence', () => {
  const interval = verifiedCoverageConfidenceInterval(longHistory);
  assert.equal(interval.confidenceLevel, .95);
  assert.equal(interval.method, 'wilson_effective_sample');
  assert.equal(interval.approximate, true);
  assert.equal(interval.effectiveSampleCount, 12);
  const independent = verifiedCoverageConfidenceInterval({ ...longHistory, effective_sample_count: 20 });
  assert.ok(interval.lower < independent.lower);
  assert.ok(interval.upper > independent.upper);
  for (const changes of [
    { covered_count: 14 }, { covered_count: 21 }, { covered_count: 14.5 },
    { covered_count: undefined }, { sample_count: 19 }, { effective_sample_count: 21 },
    { effective_sample_count: undefined },
    { coverage_uncertainty_method: undefined }, { coverage_uncertainty_approximate: false },
    { sample_basis: undefined }, { evaluation_source: 'historical_holdout' },
    { coverage_sample_count: 21 },
    { coverage_uncertainty_validated: false }, { coverage_uncertainty_validated: undefined },
  ]) assert.equal(verifiedCoverageConfidenceInterval({ ...longHistory, ...changes }), null);
});

test('malformed sample counts do not establish confidence evidence', () => {
  for (const sample_count of [Infinity, NaN, 20.5, -20]) {
    assert.equal(verifiedRangeHitRate({ ...longHistory, sample_count }), null);
    assert.equal(verifiedLongRangeHitRate({ ...longHistory, sample_count }), null);
  }
});

test('range hit rate rejects inconsistent counts before rendering a percentage', () => {
  for (const changes of [{ covered_count: 14 }, { covered_count: 21 },
    { covered_count: -1 }, { covered_count: 15.5 }, { coverage_sample_count: 21 }]) {
    assert.equal(verifiedRangeHitRate({ ...longHistory, ...changes }), null);
    assert.equal(verifiedLongRangeHitRate({ ...longHistory, ...changes }), null);
  }
});
