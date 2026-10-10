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
    exports, process, console, Response, URL, Deno: { env: { get: () => '' } },
    require: (name) => {
      if (Object.hasOwn(imports, name)) return imports[name];
      throw new Error(`Unexpected eager import: ${name}`);
    },
  });
  return exports;
}

function edgeHandler(resolveQuery) {
  let handler;
  const client = { from(table) {
    const state = { table, filters: {} };
    const query = {
      select(columns) { state.columns = columns; return this; },
      order() { return this; }, gte() { return this; }, limit() { return this; },
      eq(key, value) { state.filters[key] = value; return this; },
      range() { return Promise.resolve(resolveQuery(state)); },
      maybeSingle() { return Promise.resolve(resolveQuery(state)); },
      then(resolve, reject) { return Promise.resolve(resolveQuery(state)).then(resolve, reject); },
    };
    return query;
  } };
  loadModule('../supabase/functions/foodcast/index.ts', {
    'https://deno.land/std@0.168.0/http/server.ts': { serve: fn => { handler = fn; } },
    'https://esm.sh/@supabase/supabase-js@2.42.0': { createClient: () => client },
    './dashboard.ts': loadModule('../supabase/functions/foodcast/dashboard.ts'),
    './forecast.ts': loadModule('../supabase/functions/foodcast/forecast.ts'),
    './status.ts': loadModule('../supabase/functions/foodcast/status.ts'),
  });
  return handler;
}

test('forecast status route serves saved metrics without reading observed prices', async () => {
  const tables = [];
  const metrics = { evaluation_source: 'chronological_validation', sample_count: 100 };
  const handler = edgeHandler(query => {
    tables.push(query.table);
    assert.equal(query.table, 'forecast_runs');
    return { data: { model_run_id: 'saved-model', generated_at: '2026-10-09',
      horizon: 30, row_count: 3961, metrics }, error: null };
  });
  const response = await handler(new Request('https://example.test/forecast-status'));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.deepEqual(body.metrics, metrics);
  assert.deepEqual(body.modelMetrics, metrics);
  assert.deepEqual(tables, ['forecast_runs']);
});

test('product endpoint supplies immutable forecast origin and model required by horizon chart', async () => {
  const queries = [];
  const handler = edgeHandler(query => {
    queries.push(query);
    const identity = { product_name: 'Lettuce', product_variant: 'Romaine', origin: 'Local', unit: 'kg', product_category: 'Vegetables' };
    const data = {
      products: [{ id: 'lettuce', name: 'Lettuce', variant: 'Romaine', origin: 'Local', unit: 'kg', category: 'Vegetables' }],
      food_prices: [1, 2].map(day => ({ ...identity, report_date: `2026-10-0${day}`, price_index: 283.26 })),
      forecast_runs: { id: 'vintage-a', model_run_id: 'model-a', metrics: {} },
      forecast_values: [{ product_id: 'lettuce', prediction_date: '2026-10-03', predicted_price: 287.90 }],
    }[query.table];
    assert.ok(data, `unexpected table ${query.table}`);
    return { data, error: null };
  });
  const response = await handler(new Request('https://example.test/products'));
  assert.equal(response.status, 200);
  const [product] = await response.json();
  assert.equal(product.forecastOriginDate, '2026-10-02');
  assert.equal(product.forecastModelRunId, 'model-a');
  assert.equal(product.forecastData.at(-1).predicted, 287.90);
  assert.equal(queries.find(q => q.table === 'forecast_values').filters.run_id, 'vintage-a');
  const { forecastHorizonPoints } = loadModule('app/lib/data.ts');
  assert.equal(forecastHorizonPoints(product.forecastData, product.forecastOriginDate, 'daily')[0].predicted, 287.90);
});

test('news remains readable before the additive provenance migration is installed', async () => {
  const handler = edgeHandler(query => query.columns.includes('publication_precision')
    ? { data: null, error: { code: '42703', message: 'column news_articles.published_date does not exist' } }
    : { data: [{ id: 'article', title: 'Price report', content: 'Report', published_at: '2026-10-01T00:00:00Z' }], error: null });
  const response = await handler(new Request('https://example.test/news'));
  assert.equal(response.status, 200);
  const [article] = await response.json();
  assert.equal(article.title, 'Price report');
  assert.equal(article.date, 'Publication date unavailable');
});

test('dashboard projection preserves card/search fields and excludes chart data', () => {
  const { toDashboardProduct } = loadModule('app/lib/data.ts');
  const expected = {
    id: 'rice-1', name: 'Rice', category: 'Grains', image: '/rice.jpg',
    variant: 'Premium', origin: 'Local', currentPrice: 0, predictedPrice: 55, unit: 'kg',
    forecastSource: 'model', lastActualDate: '2026-09-24', forecastDate: '2026-09-25',
  };
  const product = Object.freeze({ ...expected, description: 'Full detail', forecastData: [{ actual: 50 }], dailyForecast: [{ date: '2026-09-25', predicted_price: 55, reasoning: 'Detail' }], sparklineData: [{ value: 50 }] });
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
  assert.equal(calls[2].options.revalidateOnMount, true);
  assert.equal(calls[2].key, 'supabase_products_v6_horizons');
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

test('forecast selection excludes expired dates and returns point prices without intervals', () => {
  const { selectFuturePredictions } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const selected = selectFuturePredictions([
    { prediction_date: '2026-09-23', predicted_price: 90 },
    { prediction_date: '2026-09-24', predicted_price: 91 },
    { prediction_date: '2026-09-27', predicted_price: 95 },
    { prediction_date: '2026-09-25T00:00:00Z', predicted_price: 93 },
    { prediction_date: '2026-09-25', predicted_price: 94 },
    { prediction_date: 'invalid', predicted_price: 100 },
    { prediction_date: '2026-09-26', predicted_price: 94.5 },
  ], '2026-09-24');

  assert.deepEqual(JSON.parse(JSON.stringify(selected)), [
    { date: '2026-09-25', predicted_price: 94, confidence_score: null, confidence_level: 'Insufficient data' },
    { date: '2026-09-26', predicted_price: 94.5, confidence_score: null, confidence_level: 'Insufficient data' },
    { date: '2026-09-27', predicted_price: 95, confidence_score: null, confidence_level: 'Insufficient data' },
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
    { prediction_date: '2026-09-25', predicted_price: 103 },
  ], '2026-09-24');
  const chart = buildForecastData(history, predictions);

  assert.equal(chart.some((point) => point.actual !== null && point.predicted !== null), false);
  assert.deepEqual(JSON.parse(JSON.stringify(chart.at(-1))), {
    date: '2026-09-25', name: 'Sep 25', actual: null, predicted: 103,
  });
});

test('missing forecasts leave only actual history and do not invent a future trajectory', () => {
  const { selectFuturePredictions, buildForecastData, meanFirstWeek } = loadModule('../supabase/functions/foodcast/forecast.ts');
  const forecasts = selectFuturePredictions([], '2026-12-31');
  const chart = buildForecastData([{ report_date: '2026-12-31', price_index: 100 }], forecasts);
  assert.equal(chart.length, 1);
  assert.equal(chart[0].actual, 100);
  assert.equal(chart[0].predicted, null);
  assert.equal(meanFirstWeek(forecasts, 100), 100);
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
  assert.match(edgeSource, /selectFuturePredictions\(dailyRows, lastActualDate\)/);
  assert.doesNotMatch(edgeSource, /entry\.predicted = entry\.actual/);
  assert.match(sqlSource, /prediction_date > \(r\.last_row->>'report_date'\)::date/);
  assert.match(sqlSource, /min\(p\.prediction_date\) = \(r\.last_row->>'report_date'\)::date \+ 1/);
});
