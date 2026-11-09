import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function helpers() {
  const source = fs.readFileSync(new URL('../app/lib/local-model.ts', import.meta.url), 'utf8');
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { module, exports: module.exports, URLSearchParams });
  return module.exports;
}
test('explicit incumbent overrides research default; production ignores query', () => {
  const { selectLocalResearch } = helpers();
  assert.equal(selectLocalResearch(true, ''), true);
  assert.equal(selectLocalResearch(true, '?model=incumbent'), false);
  assert.equal(selectLocalResearch(true, '?model=calendar-research'), true);
  assert.equal(selectLocalResearch(false, '?model=calendar-research'), false);
});
test('research chart contains saved rows only, preserves dates and null confidence', () => {
  const { researchChartPoints } = helpers();
  const rows = [{ horizon: 'weekly', target_start: '2026-01-05', target_end: '2026-01-11', lead: 1, prediction: 92.35, confidence_score: 99 }, { horizon: 'daily', target_start: '2026-01-02', target_end: '2026-01-02', prediction: 10, unavailable: true }];
  const points = researchChartPoints(rows);
  assert.equal(points[0].predicted, 92.35);
  assert.equal(points[0].date, '2026-01-11');
  assert.equal(points[0].actual, null);
  assert.equal(points[0].confidence_score, null);
  assert.equal(points[1].predicted, null);
  assert.equal(researchChartPoints([]).length, 0);
});
