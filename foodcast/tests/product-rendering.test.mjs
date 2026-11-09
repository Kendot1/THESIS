import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

function load(file, imports) {
  const source = fs.readFileSync(new URL(file, import.meta.url), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText;
  const exports = {};
  vm.runInNewContext(output, { exports, process, console, require: name => {
    if (Object.hasOwn(imports, name)) return imports[name];
    throw new Error(`Unexpected import ${name}`);
  }});
  return exports;
}

test('product card preloads the same SWR key consumed by the product page', () => {
  const card = fs.readFileSync(new URL('../app/components/ProductCard.tsx', import.meta.url), 'utf8');
  assert.match(card, /preload\("supabase_products_v6_horizons", fetchProducts\)/);
});

test('full server products render immediately without redundant mount fetch; stripped and empty fallbacks revalidate', () => {
  const calls = [];
  const hooks = load('../app/lib/hooks.ts', {react:{}, swr:(key, fetcher, options) => {calls.push(options);return {};}, './data':{}});
  hooks.useProducts([{id:'a',forecastData:[{date:'2026-01-01'}],dailyForecast:[]}]);
  hooks.useProducts([{id:'a',forecastData:[],dailyForecast:[]}]);
  hooks.useProducts([]);
  assert.equal(calls[0].revalidateOnMount, false);
  assert.equal(calls[1].revalidateOnMount, true);
  assert.equal(calls[2].revalidateOnMount, true);
});
