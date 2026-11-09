import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const read = file => fs.readFileSync(new URL(file, import.meta.url), 'utf8');
const load = file => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(read(file), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText,
    { module, exports: module.exports, process: { env: {} }, require: () => ({}) });
  return module.exports;
};
import {loadTs} from './load-ts.mjs';
const data = loadTs('../app/lib/data.ts');

const product = (over = {}) => ({
  id: 'p', name: 'Lettuce', variant: 'Romaine', origin: 'Local', unit: 'kg', category: 'Vegetables',
  forecastSource: 'model', forecastOriginDate: '2026-11-06', lastActualDate: '2026-11-06',
  dailyForecast: [{ date: '2026-11-07', predicted_price: 120, reasoning: '' }],
  forecastData: [{ date: '2026-11-06', name: 'Nov 6', actual: 100, predicted: null, horizon: 'daily' }],
  ...over,
});
const summary = (over = {}) => ({ id: 'p', name: 'Lettuce', variant: 'Romaine', origin: 'Local', unit: 'kg',
  forecastSource: 'model', lastActualDate: '2026-11-06', forecastDate: '2026-11-07', predictedPrice: 120, currentPrice: 100, ...over });

test('model product with a positive daily prediction after origin is shown', () => {
  assert.equal(data.hasModelPrediction(product()), true);
  // forecastData daily point alone is sufficient (dailyForecast stripped).
  assert.equal(data.hasModelPrediction(product({ dailyForecast: [],
    forecastData: [{ date: '2026-11-07', actual: null, predicted: 118, horizon: 'daily' }] })), true);
});

test('trend_fallback and missing source are hidden even with prices', () => {
  assert.equal(data.hasModelPrediction(product({ forecastSource: 'trend_fallback' })), false);
  assert.equal(data.hasModelPrediction(product({ forecastSource: undefined })), false);
  assert.equal(data.hasModelPrediction(null), false);
});

test('model product with empty forecast is hidden', () => {
  assert.equal(data.hasModelPrediction(product({ dailyForecast: [], forecastData: [] })), false);
  assert.equal(data.hasModelPrediction(product({ dailyForecast: undefined, forecastData: undefined })), false);
});

test('NaN, zero, negative, null, and on/before-origin prices are hidden', () => {
  for (const bad of [NaN, 0, -5, null, Infinity, '120']) {
    assert.equal(data.hasModelPrediction(product({ dailyForecast: [{ date: '2026-11-07', predicted_price: bad }] })), false, String(bad));
  }
  assert.equal(data.hasModelPrediction(product({ dailyForecast: [{ date: '2026-11-06', predicted_price: 120 }] })), false);
  // Weekly/monthly-only predictions do not count as a daily model prediction.
  assert.equal(data.hasModelPrediction(product({ dailyForecast: [],
    forecastData: [{ date: '2026-11-13', actual: null, predicted: 130, horizon: 'weekly' }] })), false);
});

test('model product missing weekly/monthly rows remains visible', () => {
  const p = product({ forecastData: [{ date: '2026-11-07', actual: null, predicted: 118, horizon: 'daily' }] });
  assert.equal(data.hasModelPrediction(p), true);
});

test('identities are filtered independently by variant and unit', () => {
  const list = [
    product({ id: 'kg', unit: 'kg' }),
    product({ id: 'pc', unit: 'piece', forecastSource: 'trend_fallback' }),
    product({ id: 'iceberg', variant: 'Iceberg', dailyForecast: [] }),
  ];
  assert.equal(JSON.stringify(data.filterDisplayableProducts(list).map(p => p.id)), '["kg"]');
  assert.equal(data.filterDisplayableProducts(undefined).length, 0);
});

test('dashboard summary keeps products with valid recent prices even when forecast rows are missing', () => {
  assert.equal(data.hasDashboardModelPrediction(summary()), true);
  assert.equal(data.hasDashboardModelPrediction(summary({ forecastSource: 'trend_fallback' })), true);
  assert.equal(data.hasDashboardModelPrediction(summary({ forecastDate: null })), true);
  assert.equal(data.hasDashboardModelPrediction(summary({ predictedPrice: NaN })), true);
  assert.equal(data.hasDashboardModelPrediction(summary({ forecastDate: '2026-11-06' })), true);
  assert.equal(data.hasDashboardModelPrediction(summary({ currentPrice: 0 })), false);
  assert.equal(data.hasDashboardModelPrediction(summary({ lastActualDate: null })), false);
  assert.equal(JSON.stringify(data.filterDisplayableDashboardProducts([summary({ id: 'a' }), summary({ id: 'b', unit: 'piece', forecastSource: 'trend_fallback' })]).map(p => p.id)), '["a","b"]');
  // toDashboardProduct of a full model product passes; fallback still has valid market history.
  assert.equal(data.hasDashboardModelPrediction(data.toDashboardProduct(product())), true);
  assert.equal(data.hasDashboardModelPrediction(data.toDashboardProduct(product({ forecastSource: 'trend_fallback' }))), true);
});

test('every product source in data.ts applies the shared filter', () => {
  const src = read('../app/lib/data.ts');
  const body = name => src.slice(src.indexOf(`export async function ${name}(`), src.indexOf('\n}\n', src.indexOf(`export async function ${name}(`)));
  assert.match(body('fetchProducts'), /filterDisplayableProducts\(await edgeFetch/);
  assert.match(body('fetchLiveProducts'), /filterDisplayableProducts\(await fetchFromNetwork/);
  const dash = body('fetchDashboardProducts');
  assert.equal((dash.match(/return filterDisplayableDashboardProducts\(/g) ?? []).length, 2);
  assert.match(body('fetchProductById'), /fetchProducts\(\)/);
  assert.match(read('../app/lib/hooks.ts'), /displayableCache\(getSyncCache<Product\[\]>\("products"\)\)/);
});

test('every page/API entry point obtains products only through the filtered fetchers', () => {
  const full = ['../app/Predict/page.tsx', '../app/MarketData/page.tsx', '../app/Map/page.tsx', '../app/Product/[id]/page.tsx', '../app/tags/[id]/page.tsx'];
  for (const file of full) assert.match(read(file), /fetchProducts\(\)/, file);
  const dashboard = ['../app/page.tsx', '../app/About/page.tsx', '../app/api/dashboard/products/route.ts'];
  for (const file of dashboard) assert.match(read(file), /fetchDashboardProducts\(\)/, file);
  // Client views read products only via useProducts/useDashboardProducts (filtered fetchers)
  // and comparisons via fetchLiveProducts; none reach the edge 'products' path directly.
  const clients = { '../app/client/Home.tsx': /useDashboardProducts\(/, '../app/client/About.tsx': /useDashboardProducts\(/,
    '../app/client/Predict.tsx': /useProducts\(/, '../app/client/MarketData.tsx': /useProducts\(/, '../app/client/Product.tsx': /useProducts\(/,
    '../app/components/ProductComparison.tsx': /fetchLiveProducts\(\)/ };
  for (const [file, pattern] of Object.entries(clients)) {
    const src = read(file);
    assert.match(src, pattern, file);
    assert.doesNotMatch(src, /functions\/v1\/foodcast|edgeFetch|fetchFromNetwork/, file);
  }
  // Product detail resolves the id from the filtered list → existing not-found state.
  assert.match(read('../app/client/Product.tsx'), /products\.find\(\(p\) => p\.id === id\) \?\? null/);
  assert.match(read('../app/client/Product.tsx'), /t\("productNotFound"\)/);
});
