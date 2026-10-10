import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildForecastSequenceData,
  resolveForecastOrigin,
  selectFuturePredictions,
  selectSavedPeriodPredictions,
} from './forecast.ts';

const origin = '2026-09-27';
const history = Array.from({ length: 14 }, (_, index) => {
  const date = new Date(Date.parse(origin + 'T00:00:00Z') - (13 - index) * 86400000)
    .toISOString().slice(0, 10);
  return { report_date: date, price_index: 50 + index };
});
const predictions = Array.from({ length: 30 }, (_, index) => ({
  date: new Date(Date.parse(origin + 'T00:00:00Z') + (index + 1) * 86400000)
    .toISOString().slice(0, 10),
  predicted_price: 101 + index,
}));
const savedPeriods = [
  ...[
    ['2026-09-28', '2026-10-04', '2026-10-04', 104, 7, 7],
    ['2026-10-05', '2026-10-11', '2026-10-11', 111, 7, 7],
    ['2026-10-12', '2026-10-18', '2026-10-18', 118, 7, 7],
    ['2026-10-19', '2026-10-25', '2026-10-25', 125, 7, 7],
    ['2026-10-26', '2026-11-01', '2026-10-27', 129.5, 2, 7],
  ].map(([start, end, date, predicted_price, covered_days, period_days], index) => ({
    forecast_horizon: 'weekly', target_period_start: start, target_period_end: end, date,
    predicted_price, forecast_step: index + 1, covered_days, period_days,
  })),
  ...[
    ['2026-09-01', '2026-09-30', '2026-09-30', 102, 3, 30],
    ['2026-10-01', '2026-10-31', '2026-10-27', 117, 27, 31],
  ].map(([start, end, date, predicted_price, covered_days, period_days], index) => ({
    forecast_horizon: 'monthly', target_period_start: start, target_period_end: end, date,
    predicted_price, forecast_step: index + 1, covered_days, period_days,
  })),
];

test('charts persisted weekly and monthly points with full period bounds and partial coverage', () => {
  const data = buildForecastSequenceData(history, predictions, origin, savedPeriods);
  const daily = data.filter(point => point.horizon === 'daily' && point.predicted != null);
  const weekly = data.filter(point => point.horizon === 'weekly' && point.predicted != null);
  const monthly = data.filter(point => point.horizon === 'monthly' && point.predicted != null);

  assert.equal(daily.length, 30);
  assert.deepEqual(weekly.map(point => [point.target_period_start, point.target_period_end,
    point.covered_days, point.period_days, point.predicted]), [
    ['2026-09-28', '2026-10-04', 7, 7, 104],
    ['2026-10-05', '2026-10-11', 7, 7, 111],
    ['2026-10-12', '2026-10-18', 7, 7, 118],
    ['2026-10-19', '2026-10-25', 7, 7, 125],
    ['2026-10-26', '2026-11-01', 2, 7, 129.5],
  ]);
  assert.equal(weekly[4].date, '2026-10-27');
  assert.match(weekly[4].name, /partial/);
  assert.deepEqual(monthly.map(point => [point.target_period_start, point.target_period_end,
    point.covered_days, point.period_days, point.predicted]), [
    ['2026-09-01', '2026-09-30', 3, 30, 102],
    ['2026-10-01', '2026-10-31', 27, 31, 117],
  ]);
  assert.equal(monthly[1].date, '2026-10-27');
});

test('daily path alone cannot be relabeled or averaged into weekly and monthly forecasts', () => {
  const data = buildForecastSequenceData(history, predictions, origin);
  assert.equal(data.filter(point => point.horizon === 'daily' && point.predicted != null).length, 30);
  assert.equal(data.filter(point => point.horizon === 'weekly' && point.predicted != null).length, 0);
  assert.equal(data.filter(point => point.horizon === 'monthly' && point.predicted != null).length, 0);
});

test('historical weekly values use calendar averages and omit an open month actual', () => {
  const data = buildForecastSequenceData(history, predictions, origin, savedPeriods);
  const weeklyActuals = data.filter(point => point.horizon === 'weekly' && point.actual != null);
  const monthlyActuals = data.filter(point => point.horizon === 'monthly' && point.actual != null);
  assert.deepEqual(weeklyActuals.map(point => [point.target_period_start, point.target_period_end,
    point.actual, point.covered_days]), [
    ['2026-09-14', '2026-09-20', 53, 7],
    ['2026-09-21', '2026-09-27', 60, 7],
  ]);
  assert.deepEqual(monthlyActuals, []);
});

test('duplicate actual observations are averaged before calendar actual points are made', () => {
  const duplicated = [...history, { report_date: '2026-09-27', price_index: 80 }];
  const data = buildForecastSequenceData(duplicated, predictions, origin, savedPeriods);
  const latestDaily = data.find(point => point.horizon === 'daily' && point.date === origin);
  const latestWeeklyActual = data.find(point => point.horizon === 'weekly' && point.actual != null
    && point.target_period_end === origin);
  assert.equal(latestDaily.actual, 71.5);
  assert.equal(latestWeeklyActual.covered_days, 7);
  assert.equal(latestWeeklyActual.actual, 61.21);
});

test('saved forecast origin keeps predictions aligned when product data trails the issue date', () => {
  const forecastOrigin = resolveForecastOrigin('2026-10-01', '2026-10-05');
  const rows = Array.from({ length: 30 }, (_, index) => ({
    prediction_date: new Date(Date.parse(forecastOrigin + 'T00:00:00Z')
      + (index + 1) * 86400000).toISOString().slice(0, 10),
    forecast_origin_date: forecastOrigin,
    predicted_price: 101 + index,
  }));

  const selected = selectFuturePredictions(rows, forecastOrigin);
  assert.equal(forecastOrigin, '2026-10-05');
  assert.equal(selected.length, 30);
  assert.equal(selected[0].date, '2026-10-06');
});

test('stale forecast origins fall back to the latest actual date and old paths are rejected', () => {
  const forecastOrigin = resolveForecastOrigin('2026-10-05', '2026-10-01');
  const oldRows = Array.from({ length: 30 }, (_, index) => ({
    prediction_date: new Date(Date.parse('2026-10-01T00:00:00Z')
      + (index + 1) * 86400000).toISOString().slice(0, 10),
    forecast_origin_date: '2026-10-01',
    predicted_price: 101 + index,
  }));

  assert.equal(forecastOrigin, '2026-10-05');
  assert.deepEqual(selectFuturePredictions(oldRows, forecastOrigin), []);
});

test('stored period points follow a current saved origin even if last actual date is older', () => {
  const rows = [{
    prediction_date: '2026-10-11', forecast_origin_date: '2026-10-05',
    forecast_horizon: 'weekly', target_period_start: '2026-10-05',
    target_period_end: '2026-10-11', predicted_price: 111,
    forecast_step: 1, covered_days: 6, period_days: 7,
  }];

  assert.deepEqual(selectSavedPeriodPredictions(rows, '2026-10-05', true), rows);
  assert.deepEqual(selectSavedPeriodPredictions(rows, '2026-10-12', true), []);
  assert.deepEqual(selectSavedPeriodPredictions(rows, '2026-10-05', false), []);
});
