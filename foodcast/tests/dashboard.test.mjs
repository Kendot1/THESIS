import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the actual TypeScript modules without introducing a test framework.
function loadModule(file, imports = {}) {
  const source = fs.readFileSync(fileURLToPath(new URL('../' + file, import.meta.url)), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  });
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, process, console, Response,
    require: (name) => {
      if (Object.hasOwn(imports, name)) return imports[name];
      throw new Error(`Unexpected eager import: ${name}`);
    },
  });
  return exports;
}

test('dashboard projection preserves card/search fields and excludes chart data', () => {
  const { toDashboardProduct } = loadModule('app/lib/data.ts');
  const expected = {
    id: 'rice-1', name: 'Rice', category: 'Grains', image: '/rice.jpg',
    variant: 'Premium', origin: 'Local', currentPrice: 0, predictedPrice: 55, unit: 'kg',
    forecastSource: 'model',
  };
  const product = Object.freeze({ ...expected, description: 'Full detail', forecastData: [{ actual: 50 }], dailyForecast: [{ reasoning: 'Detail' }], sparklineData: [{ value: 50 }] });
  assert.deepEqual(JSON.parse(JSON.stringify(toDashboardProduct(product))), expected);
  assert.equal(product.forecastData.length, 1);
});

test('prediction identity includes normalized unit', () => {
  const { normalizeSeriesUnit, productSeriesKey } = loadModule('../supabase/functions/foodcast/dashboard.ts');
  assert.equal(normalizeSeriesUnit({ unit: 'per kg' }), 'kg');
  assert.equal(normalizeSeriesUnit({ category: 'Oils', variant: '1L', unit: 'bottle' }), 'liter');
  assert.equal(normalizeSeriesUnit({ name: 'Chicken Egg', unit: 'kg' }), 'piece');
  assert.notEqual(
    productSeriesKey({ name: 'Oil', variant: 'Standard', origin: 'Local', unit: 'liter' }),
    productSeriesKey({ name: 'Oil', variant: 'Standard', origin: 'Local', unit: 'bottle' }),
  );
});

test('dashboard SWR cache is isolated and retries empty server fallback only', async () => {
  const calls = [];
  const hooks = loadModule('app/lib/hooks.ts', {
    react: {},
    swr: (key, fetcher, options) => { calls.push({ key, fetcher, options }); return {}; },
    './data': {},
  });
  const products = [{ id: 'rice-1' }];
  hooks.useDashboardProducts(products);
  hooks.useDashboardProducts([]);
  hooks.useProducts([]);
  assert.equal(calls[0].options.fallbackData, products);
  assert.equal(calls[0].options.revalidateOnMount, false);
  assert.equal(calls[0].options.refreshInterval, 60 * 1000);
  assert.equal(calls[1].options.revalidateOnMount, true);
  assert.notEqual(calls[0].key, calls[2].key);
});

test('summary API caches successful responses and exposes failures for SWR retry', async () => {
  let products = [{ id: 'rice-1' }];
  const route = loadModule('app/api/dashboard/products/route.ts', {
    '../../../lib/data': { fetchDashboardProducts: async () => products },
  });
  const success = await route.GET();
  assert.equal(success.status, 200);
  assert.deepEqual(await success.json(), products);
  assert.match(success.headers.get('cache-control'), /no-store/);
  products = [];
  const failure = await route.GET();
  assert.equal(failure.status, 503);
  assert.equal(failure.headers.get('cache-control'), null);
});

test('forecast selection excludes actual and expired dates, sorts, deduplicates, and clamps intervals', () => {
  const { selectFuturePredictions } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const selected = selectFuturePredictions([
    { prediction_date: '2026-09-23', predicted_price: 90, lower_bound: 80, upper_bound: 100 },
    { prediction_date: '2026-09-24', predicted_price: 91, lower_bound: 80, upper_bound: 100 },
    { prediction_date: '2026-09-27', predicted_price: 95, lower_bound: 97, upper_bound: 92 },
    { prediction_date: '2026-09-25T00:00:00Z', predicted_price: 93, lower_bound: 88, upper_bound: 98 },
    { prediction_date: '2026-09-25', predicted_price: 94, lower_bound: 89, upper_bound: 99 },
    { prediction_date: 'invalid', predicted_price: 100 },
    { prediction_date: '2026-09-26', predicted_price: 94.5, lower_bound: 90, upper_bound: 98 },
  ], '2026-09-24');

  assert.deepEqual(JSON.parse(JSON.stringify(selected)), [
    { date: '2026-09-25', predicted_price: 94, lower_bound: 89, upper_bound: 99 },
    { date: '2026-09-26', predicted_price: 94.5, lower_bound: 90, upper_bound: 98 },
    { date: '2026-09-27', predicted_price: 95, lower_bound: 95, upper_bound: 95 },
  ]);
});

test('a stale forecast tail is rejected instead of being presented as a fresh run', () => {
  const { selectFuturePredictions } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const selected = selectFuturePredictions([
    { prediction_date: '2026-09-28', predicted_price: 101 },
    { prediction_date: '2026-09-29', predicted_price: 102 },
  ], '2026-09-24');
  assert.deepEqual(JSON.parse(JSON.stringify(selected)), []);
});

test('forecast chart data never marks one date as both actual and predicted', () => {
  const { buildForecastData, selectFuturePredictions } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const history = [
    { report_date: '2026-09-23', price_index: 100 },
    { report_date: '2026-09-24', price_index: 102 },
  ];
  const predictions = selectFuturePredictions([
    { prediction_date: '2026-09-24', predicted_price: 101 },
    { prediction_date: '2026-09-25', predicted_price: 103, lower_bound: 98, upper_bound: 108 },
  ], '2026-09-24');
  const chart = buildForecastData(history, predictions);

  assert.equal(chart.some((point) => point.actual !== null && point.predicted !== null), false);
  assert.deepEqual(JSON.parse(JSON.stringify(chart.at(-1))), {
    date: '2026-09-25', name: 'Sep 25', actual: null, predicted: 103, lower: 98, upper: 108,
  });
});

test('fallback uses persistence instead of inventing a trend', () => {
  const { makeTrendFallback, meanFirstWeek } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const forecast = makeTrendFallback('2026-12-31', 100, [94, 95, 96, 97, 98, 99, 100]);
  assert.equal(forecast.length, 30);
  assert.equal(forecast[0].date, '2027-01-01');
  assert.equal(forecast.at(-1).date, '2027-01-30');
  assert.equal(forecast[0].predicted_price, 100);
  assert.equal(forecast.at(-1).predicted_price, 100);
  assert.equal(meanFirstWeek(forecast, 100), 100);
  assert.equal(forecast.every((row) => row.lower_bound === null && row.upper_bound === null), true);
});

test('fallback stays at persistence when sparse data would create a runaway forecast', () => {
  const { makeTrendFallback } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const forecast = makeTrendFallback('2025-12-29', 408.33, [385.71, 408.33]);
  assert.equal(forecast[0].predicted_price, 408.33);
  assert.equal(forecast.at(-1).predicted_price, 408.33);
});

test('dashboard summary does not turn a missing model into a trading signal', () => {
  const { mapDashboardSummary } = loadModule('../supabase/functions/foodcast/dashboard.ts');
  const row = {
    first_row: { product_name: 'Garlic', product_variant: 'Standard', origin: 'Local', product_category: 'Vegetables', price_index: 400, unit: 'kg' },
    last_row: { product_name: 'Garlic', product_variant: 'Standard', origin: 'Local', product_category: 'Vegetables', price_index: 408.33, unit: 'kg' },
    meta: { id: 'garlic-local', category: 'Vegetables', image_url: null },
    recent_prices: [385.71, 408.33],
    prediction_prices: [],
  };
  const [product] = mapDashboardSummary([row], {
    slugify: (value) => value,
    defaultImage: '/fallback.jpg',
  });
  assert.equal(product.predictedPrice, 408.33);
  assert.equal(product.forecastSource, 'trend_fallback');
  assert.equal(product.unit, 'kg');
});

test('edge and SQL paths enforce the same future-only forecast boundary', () => {
  const edgeSource = fs.readFileSync(fileURLToPath(new URL('../../supabase/functions/foodcast/index.ts', import.meta.url)), 'utf8');
  const sqlSource = fs.readFileSync(fileURLToPath(new URL('../../supabase/migrations/202609250002_unit_aware_dashboard_summary.sql', import.meta.url)), 'utf8');
  assert.match(edgeSource, /selectFuturePredictions\(allPredictions, lastActualDate\)/);
  assert.doesNotMatch(edgeSource, /entry\.predicted = entry\.actual/);
  assert.match(sqlSource, /prediction_date > \(r\.last_row->>'report_date'\)::date/);
  assert.match(sqlSource, /min\(p\.prediction_date\) = \(r\.last_row->>'report_date'\)::date \+ 1/);
});
