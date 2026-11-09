import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
const require = createRequire(import.meta.url);
function load(file, overrides = {}, env = 'development') {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(code, { module: loaded, exports: loaded.exports, process: { env: { NODE_ENV: env } }, require: name => name === 'server-only' ? {} : name in overrides ? overrides[name] : require(name) });
  return loaded.exports;
}
test('production reader refuses file access', async () => {
  let reads = 0;
  const { readStagingForecasts } = load('../app/research-model-test/staging.ts', { 'node:fs/promises': { readFile: () => { reads++; throw new Error('must not read'); } } }, 'production');
  await assert.rejects(readStagingForecasts(), /development-only/);
  assert.equal(reads, 0);
});
test('production page returns notFound before loading saved forecasts', async () => {
  let reads = 0;
  const { default: Page } = load('../app/research-model-test/page.tsx', {
    'next/navigation': { notFound: () => { throw new Error('NEXT_NOT_FOUND'); } },
    './staging': { readStagingForecasts: () => { reads++; throw new Error('must not read'); } },
  }, 'production');
  await assert.rejects(Page({ searchParams: Promise.resolve({}) }), /NEXT_NOT_FOUND/);
  assert.equal(reads, 0);
});
test('saved staging reader loads only three approved files and retains full identity and null confidence', async () => {
  const { readStagingForecasts } = load('../app/research-model-test/staging.ts');
  const rows = await readStagingForecasts();
  assert.equal(rows.length, 1272);
  assert.equal(new Set(rows.map(r => r.series)).size, 106);
  assert.ok(rows.every(r => r.forecast_origin === '2026-01-01' && r.confidence_score === null));
  assert.ok(rows.some(r => r.fallback));
  assert.ok(rows.some(r => !r.fallback));
});
