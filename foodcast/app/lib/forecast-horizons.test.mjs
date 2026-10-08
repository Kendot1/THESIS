import assert from 'node:assert/strict';
import test from 'node:test';
import { forecastTargetDate, forecastHorizonPoints, productHorizonConfidence } from './data.ts';

const productId = 'f186c4cf-7f6d-4c51-babf-310596270988';
const origin = '2026-09-27';
const data = [1, 3, 7, 30].map(lead => ({
  date: new Date(Date.parse(origin + 'T00:00:00Z') + lead * 86400000).toISOString().slice(0, 10),
  name: '', actual: null, predicted: 50 + lead,
}));
const product = { id: productId, forecastSource: 'model', forecastOriginDate: origin,
  forecastModelRunId: 'model-a', lastActualDate: origin, forecastData: data };
const metric = { forecast_horizon_days: 7, confidence_score: 92.4, confidence_level: 'Very High',
  mae: 2, rmse: 3, mape: 4, sample_count: 30, model_version: 'model-a',
  evaluation_source: 'chronological_validation', evidence_status: 'validated', confidence_method: 'backend-method' };
function status(changes = {}) {
  return { modelRunId: 'model-a', modelMetrics: { product_metrics: {
    [productId]: { confidence_by_horizon: { weekly: { ...metric, ...changes } } },
  } } };
}

test('calendar horizons preserve exact dates and prices despite gaps and month boundaries', () => {
  assert.equal(forecastTargetDate(origin, 'daily'), '2026-09-28');
  assert.equal(forecastTargetDate(origin, 'weekly'), '2026-10-04');
  assert.equal(forecastTargetDate(origin, 'monthly'), '2026-10-27');
  assert.deepEqual(forecastHorizonPoints([...data].reverse(), origin, 'weekly'), [data[2]]);
  assert.deepEqual(forecastHorizonPoints(data.filter(row => row !== data[2]), origin, 'weekly'), []);
  assert.equal(forecastTargetDate('2026-02-30', 'daily'), null);
  assert.deepEqual(forecastHorizonPoints(data, undefined, 'monthly'), []);
});

test('daily, weekly and monthly sample genuine prices at 1/7/30 day cadence', () => {
  const fullPath = Array.from({ length: 30 }, (_, index) => ({
    date: new Date(Date.parse(origin + 'T00:00:00Z') + (index + 1) * 86400000).toISOString().slice(0, 10),
    name: '', actual: null, predicted: 100 + index,
  }));
  assert.deepEqual(forecastHorizonPoints(fullPath, origin, 'daily'), fullPath);
  assert.deepEqual(forecastHorizonPoints(fullPath, origin, 'weekly'), [6, 13, 20, 27].map(index => fullPath[index]));
  assert.deepEqual(forecastHorizonPoints(fullPath, origin, 'monthly'), [fullPath[29]]);
  const missingWeek = fullPath.filter((_, index) => index !== 13);
  assert.deepEqual(forecastHorizonPoints(missingWeek, origin, 'weekly'), [6, 20, 27].map(index => fullPath[index]));
  assert.deepEqual(forecastHorizonPoints(fullPath.slice(0, 29), origin, 'monthly'), []);
});

test('backend confidence belongs to one exact product, horizon and model', () => {
  assert.deepEqual(productHorizonConfidence(product, status(), 'weekly'), metric);
  assert.equal(productHorizonConfidence(product, status(), 'daily'), null);
  assert.equal(productHorizonConfidence({ ...product, id: 'different-product' }, status(), 'weekly'), null);
  assert.equal(productHorizonConfidence(product, { ...status(), modelRunId: 'model-b' }, 'weekly'), null);
  assert.equal(productHorizonConfidence({ ...product, forecastSource: 'trend_fallback' }, status(), 'weekly'), null);
  assert.equal(productHorizonConfidence({ ...product, lastActualDate: '2026-10-04' }, status(), 'weekly'), null);
  assert.equal(productHorizonConfidence({ ...product, forecastData: data.slice(0, 2) }, status(), 'weekly'), null);
});

test('remaining forecasts stay visible after newer actuals arrive without moving saved target dates', () => {
  const remaining = data.filter(point => point.date > '2026-10-05');
  const daily = forecastHorizonPoints(remaining, origin, 'daily');
  assert.equal(daily[0].date, '2026-10-27');
  assert.equal(daily[0].predicted, 80);
  assert.equal(forecastTargetDate(origin, 'daily'), '2026-09-28');
  assert.equal(productHorizonConfidence({ ...product, lastActualDate: '2026-10-05', forecastData: remaining }, status(), 'weekly'), null);
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
