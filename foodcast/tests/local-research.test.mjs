import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
const source = readFileSync(new URL('../app/api/local-research/route.ts', import.meta.url), 'utf8');
function load(env, fetch) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    { module, exports: module.exports, require: () => ({}), process: { env }, fetch, URL, Response, AbortSignal });
  return module.exports.GET;
}
const env = { NODE_ENV: 'development', FOODCAST_LOCAL_RESEARCH: 'zhwhnnxbodzrklhgsurn', FOODCAST_RESEARCH_SERVICE_KEY: 'test-private' };
const id = '91d4e52d-a5d8-410f-8fe5-4d3203f1ec57';
const request = () => new Request(`http://localhost/api/local-research?productId=${id}`);
test('production and unconfigured dev refuse access without fetch', async () => {
  for (const config of [{ ...env, NODE_ENV: 'production' }, { NODE_ENV: 'development' }]) {
    assert.equal((await load(config, () => { throw Error('unexpected fetch'); })(request())).status, 404);
  }
});
test('remote reads are GET-only, exact target, full identity, and null confidence', async () => {
  const identity = { product_name: 'Corn', product_category: 'Corn', product_variant: 'White', origin: 'Local', unit: 'kg' };
  const row = { product_series: identity, forecast_origin: '2026-01-01', prediction: 92.05, confidence_score: 99 };
  let calls = 0;
  const GET = load(env, async (url, options) => {
    calls++;
    assert.ok(url.startsWith('https://zhwhnnxbodzrklhgsurn.supabase.co/rest/v1/'));
    assert.equal(options.method, 'GET'); assert.equal(options.cache, 'no-store');
    return Response.json(url.includes('/products?') ? [{ id, name: 'Corn', category: 'Corn', variant: 'White', origin: 'Local', unit: 'kg' }] : [{
      id: '03aaf1ae-3a5b-4262-9c4c-705ec0d6b196', model_name: 'calendar_hybrid_7_4_1', evidence_class: 'RETROSPECTIVE_RESEARCH_TEST', forecast_origin: '2026-01-01',
      predictions: [row, { ...row, product_series: { ...identity, unit: 'piece' } }, { ...row, product_series: { ...identity, product_variant: '' } }],
    }]);
  });
  const result = await (await GET(request())).json();
  assert.equal(calls, 2); assert.equal(result.predictions.length, 1);
  assert.equal(result.predictions[0].prediction, 92.05); assert.equal(result.predictions[0].confidence_score, null);
  assert.equal(result.metrics, null); assert.ok(!JSON.stringify(result).includes('test-private'));
});
test('upstream failure fails closed without incumbent fallback', async () => {
  const result = await load(env, async () => { throw Error('secret upstream details'); })(request());
  assert.equal(result.status, 503); assert.ok(!(await result.text()).includes('secret'));
});
