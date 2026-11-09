import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

function loadRoute(fetchDashboardProducts) {
  const source = fs.readFileSync(new URL('../app/api/dashboard/products/route.ts', import.meta.url), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(output, { exports, Response, require: () => ({ fetchDashboardProducts }) });
  return exports.GET;
}

test('dashboard API reports an upstream failure as unavailable', async () => {
  const response = await loadRoute(async () => { throw new Error('timeout'); })();
  assert.equal(response.status, 503);
});

test('dashboard API preserves an authoritative empty result', async () => {
  const response = await loadRoute(async () => [])();
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), []);
});

test('dashboard transport failure does not trigger full product fallback', () => {
  const source = fs.readFileSync(new URL('../app/lib/data.ts', import.meta.url), 'utf8');
  const body = source.slice(source.indexOf('export async function fetchDashboardProducts'), source.indexOf('export async function fetchForecastStatus'));
  assert.doesNotMatch(body, /fetchLiveProducts\s*\(/);
});
