import assert from 'node:assert/strict';
import test from 'node:test';
import { forecastTargetDate, forecastHorizonPoints, productHorizonConfidence } from './data.ts';

const productId = 'f186c4cf-7f6d-4c51-babf-310596270988';
const origin = '2026-09-27';
const dailyPoints = Array.from({ length: 14 }, (_, index) => ({
  date: new Date(Date.parse(origin + 'T00:00:00Z') + (index + 1) * 86400000).toISOString().slice(0, 10),
  name: '', actual: null, predicted: 50 + index, horizon: 'daily', forecast_step: index + 1,
}));
const weeklyPoint = { date: '2026-10-04', name: 'Week Sep 28–Oct 4 · 7/7 forecast days',
  actual: null, predicted: 54, horizon: 'weekly', forecast_step: 1,
  target_period_start: '2026-09-28', target_period_end: '2026-10-04', covered_days: 7, period_days: 7 };
const monthlyPoint = { date: '2026-10-27', name: 'October 2026 · partial (27/31 forecast days)',
  actual: null, predicted: 67, horizon: 'monthly', forecast_step: 1,
  target_period_start: '2026-10-01', target_period_end: '2026-10-31', covered_days: 27, period_days: 31 };
const weeklyPoints = Array.from({ length: 4 }, (_, i) => {
  const date = days => new Date(Date.parse(origin + 'T00:00:00Z') + days * 86400000).toISOString().slice(0, 10);
  return { ...weeklyPoint, date: date((i + 1) * 7), target_period_start: date(i * 7 + 1), target_period_end: date((i + 1) * 7), forecast_step: i + 1 };
});
const rollingMonth = { ...monthlyPoint, date: '2026-10-27', target_period_start: '2026-09-28', target_period_end: '2026-10-27', covered_days: 30, period_days: 30 };
const data = [...dailyPoints, ...weeklyPoints, rollingMonth];
const product = { id: productId, forecastSource: 'model', forecastOriginDate: origin,
  forecastModelRunId: 'model-a', lastActualDate: origin, forecastData: data };
const metric = { forecast_horizon_days: 7, confidence_score: 92.4, confidence_level: 'Very High',
  mae: 2, rmse: 3, mape: 4, sample_count: 30, sample_origin_count: 12, model_version: 'model-a',
  evaluation_source: 'chronological_validation', evidence_status: 'validated', confidence_method: 'backend-method' };
function status(changes = {}) {
  return { modelRunId: 'model-a', modelMetrics: { product_metrics: {
    [productId]: { confidence_by_horizon: { weekly: { ...metric, ...changes } } },
  } } };
}

test('rolling leads are valid dates, while chart periods come from exact stored bounds', () => {
  assert.equal(forecastTargetDate(origin, 'daily'), '2026-09-28');
  assert.equal(forecastTargetDate(origin, 'weekly'), '2026-10-04');
  assert.equal(forecastTargetDate(origin, 'monthly'), '2026-10-27');
  assert.deepEqual(forecastHorizonPoints([...data].reverse(), origin, 'weekly'), weeklyPoints);
  assert.deepEqual(forecastHorizonPoints(data, origin, 'monthly'), [rollingMonth]);
  assert.deepEqual(forecastHorizonPoints(data, origin, 'daily'), dailyPoints.slice(0, 7));
  assert.equal(forecastTargetDate('2026-02-30', 'daily'), null);
  assert.deepEqual(forecastHorizonPoints(data, undefined, 'monthly'), []);
});

test('literal November 9 and clamped month-end/leap targets', () => {
  assert.equal(forecastTargetDate('2026-11-09', 'daily'), '2026-11-10');
  assert.equal(forecastTargetDate('2026-11-09', 'weekly'), '2026-11-16');
  assert.equal(forecastTargetDate('2026-11-09', 'monthly'), '2026-12-09');
  for (const [origin, start, end] of [
    ['2027-01-31', '2027-02-01', '2027-02-28'],
    ['2028-01-31', '2028-02-01', '2028-02-29'],
    ['2028-02-29', '2028-03-01', '2028-03-29'],
    ['2026-11-30', '2026-12-01', '2026-12-30'],
    ['2026-12-31', '2027-01-01', '2027-01-31'],
  ]) {
    assert.equal(forecastTargetDate(origin, 'monthly'), end);
    const saved = { date: end, name: 'Saved', actual: null, predicted: 123.45,
      horizon: 'monthly', target_period_start: start, target_period_end: end };
    assert.deepEqual(forecastHorizonPoints([saved], origin, 'monthly'), [saved]);
    assert.equal(forecastHorizonPoints([{ ...saved, target_period_start: origin }], origin, 'monthly').length, 0);
  }
});

test('strict rolling selection rejects duplicate, missing, inconsistent-step and partial periods', () => {
  for (const change of [{ covered_days: 6 }, { period_days: 8 }, { forecast_step: 2 },
    { target_period_start: undefined }, { target_period_end: '2026-10-03' }, { predicted: NaN }]) {
    assert.deepEqual(forecastHorizonPoints([{ ...weeklyPoints[0], ...change }, ...weeklyPoints.slice(1)], origin, 'weekly'), []);
  }
  assert.deepEqual(forecastHorizonPoints([...weeklyPoints, weeklyPoints[0]], origin, 'weekly'), []);
  assert.deepEqual(forecastHorizonPoints(weeklyPoints.slice(0, 3), origin, 'weekly'), []);
  assert.deepEqual(forecastHorizonPoints([monthlyPoint], origin, 'monthly'), []);
});

test('legacy daily values never become weekly or monthly point forecasts', () => {
  const legacy = dailyPoints.map(({ horizon, ...point }) => point);
  assert.deepEqual(forecastHorizonPoints(legacy, origin, 'daily'), legacy.slice(0, 7));
  assert.deepEqual(forecastHorizonPoints(legacy, origin, 'weekly'), []);
  assert.deepEqual(forecastHorizonPoints(legacy, origin, 'monthly'), []);
});

test('backend confidence belongs to one product, period type, and model', () => {
  assert.deepEqual(productHorizonConfidence(product, status(), 'weekly'), metric);
  assert.equal(productHorizonConfidence(product, status(), 'daily'), null);
  assert.equal(productHorizonConfidence(product, status(), 'monthly'), null);
  assert.equal(productHorizonConfidence({ ...product, id: 'different-product' }, status(), 'weekly'), null);
  assert.equal(productHorizonConfidence(product, { ...status(), modelRunId: 'model-b' }, 'weekly'), null);
  assert.equal(productHorizonConfidence({ ...product, forecastSource: 'trend_fallback' }, status(), 'weekly'), null);
  assert.equal(productHorizonConfidence({ ...product, lastActualDate: '2026-10-25' }, status(), 'weekly'), null);
  assert.equal(productHorizonConfidence({ ...product, forecastData: dailyPoints }, status(), 'weekly'), null);
});

test('unsupported provenance, missing scores and malformed metrics cannot establish confidence', () => {
  for (const changes of [
    { model_version: 'model-b' }, { evidence_status: 'unverified_provenance' },
    { evidence_status: 'insufficient_data' }, { evidence_status: undefined },
    { evaluation_source: 'historical_holdout' }, { confidence_score: null },
    { confidence_score: NaN }, { confidence_score: 101 }, { confidence_score: -1 },
    { confidence_level: 'Invented' }, { forecast_horizon_days: 1 },
    { confidence_method: '' }, { sample_count: 0 }, { sample_count: 1.5 },
    { mae: null }, { rmse: Infinity }, { mape: -1 },
  ]) assert.equal(productHorizonConfidence(product, status(changes), 'weekly'), null);
});
