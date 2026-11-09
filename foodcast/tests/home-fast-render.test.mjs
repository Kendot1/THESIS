import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

test('homepage returns without waiting on live dashboard or news', async () => {
  const source = fs.readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  let calls = 0;
  vm.runInNewContext(code, { exports, require(name) {
    if (name.includes('data')) return { fetchDashboardProducts: () => { calls++; return new Promise(() => {}); }, fetchNews: () => { calls++; return new Promise(() => {}); } };
    if (name.includes('historical-performance')) return { homepagePerformance: async () => ({ historical_forecast_accuracy_pct: null }) };
    if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }) };
    return { default: () => null };
  }});
  const result = await Promise.race([exports.default(), new Promise(resolve => setTimeout(() => resolve(null), 100))]);
  assert.ok(result, 'homepage waited for live network');
  assert.equal(calls, 0);
});
