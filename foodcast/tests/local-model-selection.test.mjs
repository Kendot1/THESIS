import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../app/client/Product.tsx', import.meta.url), 'utf8');
// Exercise the component's real initial state with minimal hook stubs.
function initialMode(env) {
  const states = [];
  const react = { use: () => ({ id: 'test' }), useMemo: () => null, useState: v => { const value = typeof v === 'function' ? v() : v; states.push(value); return [value, () => {}]; }, useRef: () => ({}), useEffect: () => {} };
  const module = { exports: {} };
  const require = id => id === 'react' ? react : id === 'react/jsx-runtime' ? { jsx: () => null, jsxs: () => null } : id.endsWith('/local-model') ? { researchChartPoints: () => [] } : id === 'next/dynamic' ? (() => null) : id.includes('LanguageContext') ? { useLanguage: () => ({ t: x => x }) } : id.endsWith('/hooks') ? { useProducts: () => ({ data: [] }), useNews: () => ({}), useForecastStatus: () => ({}), useClock: () => 0 } : id.includes('idCipher') ? { decryptId: x => x } : {};
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, require, process: { env } });
  module.exports.default({ params: Promise.resolve({ id: 'test' }) });
  // researchMode follows the two dropdown states; horizon is now shared.
  return states[states.indexOf('daily') + 4];
}
test('rolling launcher keeps retained incumbent default; research requires explicit opt-in', () => {
  assert.equal(initialMode({ NODE_ENV: 'development', NEXT_PUBLIC_FOODCAST_LOCAL_MODEL: 'rolling-research' }), false);
  const module = { exports: {} };
  const helper = fs.readFileSync(new URL('../app/lib/local-model.ts', import.meta.url), 'utf8');
  vm.runInNewContext(ts.transpileModule(helper, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { module, exports: module.exports, URLSearchParams });
  const select = module.exports.selectLocalResearch;
  assert.equal(select(true, '', 'rolling-research'), false);
  assert.equal(select(true, '?model=incumbent', 'rolling-research'), false);
  assert.equal(select(true, '?model=calendar-research', 'rolling-research'), false);
  assert.equal(select(true, '?model=rolling-research', 'rolling-research'), true);
  assert.equal(select(false, '?model=rolling-research', 'rolling-research'), false);
});
test('ordinary product route starts in research only for dedicated development launcher', () => {
  assert.equal(initialMode({ NODE_ENV: 'development', NEXT_PUBLIC_FOODCAST_LOCAL_MODEL: 'calendar-research' }), true);
  assert.equal(initialMode({ NODE_ENV: 'development' }), false);
  assert.equal(initialMode({ NODE_ENV: 'production', NEXT_PUBLIC_FOODCAST_LOCAL_MODEL: 'calendar-research' }), false);
});
