import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {loadTs} from './load-ts.mjs';
const dataHelpers = loadTs('../app/lib/data.ts');
const module = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../app/lib/market-analysis.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, { module, exports: module.exports, require: () => dataHelpers });
const marketAnalysisForecasts = (...args) => JSON.parse(JSON.stringify(module.exports.marketAnalysisForecasts(...args)));

const origin = '2026-11-09';
const point = (date, horizon, start, end, predicted = 50) => ({
  date, horizon, name: 'Saved period', actual: null, predicted,
  target_period_start: start, target_period_end: end,
});
const daily = Array.from({ length: 14 }, (_, i) => point(`2026-11-${String(10 + i).padStart(2, '0')}`, 'daily'));
const thirtyDays = Array.from({ length: 30 }, (_, i) => {
  const start = new Date('2026-11-10T00:00:00Z');
  start.setUTCDate(start.getUTCDate() + i);
  const date = start.toISOString().slice(0, 10);
  return point(date, 'daily', date, date, i + 1);
});
const product = { forecastSource: 'model', forecastOriginDate: origin, forecastData: [point(origin, 'daily', origin, origin, 0.01), ...thirtyDays] };

test('November 9 analysis derives four weekly and one 30-day average from daily predictions', () => {
  assert.deepEqual(marketAnalysisForecasts(product, 'daily').map(p => p.date), thirtyDays.slice(0, 7).map(p => p.date));
  assert.deepEqual(marketAnalysisForecasts(product, 'weekly').map(p => [p.target_period_start, p.target_period_end, p.predicted]), [
    ['2026-11-10', '2026-11-16', 4], ['2026-11-17', '2026-11-23', 11],
    ['2026-11-24', '2026-11-30', 18], ['2026-12-01', '2026-12-07', 25],
  ]);
  assert.deepEqual(marketAnalysisForecasts(product, 'monthly').map(p => [p.target_period_start, p.target_period_end, p.predicted]), [
    ['2026-11-09', '2026-12-08', 14.5],
  ]);
});

test('analysis never synthesizes period predictions or admits partial, wrong-boundary, or missing outputs', () => {
  assert.deepEqual(marketAnalysisForecasts({ ...product, forecastData: thirtyDays.slice(0, 6) }, 'weekly'), []);
  assert.deepEqual(marketAnalysisForecasts({ ...product, forecastSource: 'trend_fallback' }, 'weekly'), []);
  assert.deepEqual(marketAnalysisForecasts({ ...product, forecastData: thirtyDays.slice(0, 29) }, 'monthly'), []);
  assert.deepEqual(marketAnalysisForecasts({ ...product, forecastOriginDate: undefined }, 'daily'), []);
});

test('calendar research requires an explicit bypass; calendar rows never masquerade as rolling', () => {
  const calendar = point('2026-12-31', 'monthly', '2026-12-01', '2026-12-31');
  const p = { ...product, forecastData: [calendar] };
  assert.deepEqual(marketAnalysisForecasts(p, 'monthly'), []);
  assert.deepEqual(marketAnalysisForecasts(p, 'monthly', 'calendar_research'), [calendar]);
});

test('AI Market Analysis has its own accessible horizon selector, not legacy range filters', () => {
  const source = fs.readFileSync(new URL('../app/client/Product.tsx', import.meta.url), 'utf8');
  const section = source.split('{/* AI Market Analysis */}')[1].split('{/* Side Column')[0];
  assert.match(section, /aria-label="Analysis forecast horizon"/);
  assert.match(section, /setAnalysisHorizon\(period\)/);
  assert.match(section, /aria-pressed=\{analysisHorizon === period\}/);
  assert.doesNotMatch(source, /forecastRange|filteredForecasts|3 Days|7 Days|This Month|All Time/);
  assert.match(section, /forecastPeriodUnavailable/);
  assert.match(source, /className="min-w-0 lg:col-span-8 space-y-8"/);
});
