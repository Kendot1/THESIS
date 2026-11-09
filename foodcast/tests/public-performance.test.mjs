import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const source = readFileSync('app/lib/historical-performance.server.ts', 'utf8').replace('import "server-only";', '');
const snapshot = JSON.parse(readFileSync('app/lib/historical-accuracy.json','utf8'));
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
function load(value) {
  const code = ts.transpile(source, {module:ts.ModuleKind.CommonJS, esModuleInterop:true, target:ts.ScriptTarget.ES2022});
  const exports={};new Function('exports','require',code)(exports,name=>name==='./historical-accuracy.json'?value:require(name));return exports;
}
test('homepage uses 100 minus saved daily MAPE, not cross-contract mean or hit rate',async()=>{
  const evaluation=JSON.parse(readFileSync('../audits/product_accuracy_v1/results/MODEL_ACCURACY.json','utf8'));
  assert.ok(Math.abs((await load(snapshot).homepagePerformance()).historical_forecast_accuracy_pct-(100-evaluation.models.daily.mape_pct))<1e-10);
  assert.equal(snapshot.contract_id,'historical_archived_daily14_leads1_to7');
  assert.deepEqual(await load({default:{input_hashes:{}}}).homepagePerformance(),{historical_forecast_accuracy_pct:null});
});
test('product probability remains null independent of homepage accuracy',()=>{
  assert.ok(readFileSync('app/lib/public-performance.ts','utf8').includes('confidence_pct: null'));
  const home=readFileSync('app/client/Home.tsx','utf8');
  const product=readFileSync('app/client/Product.tsx','utf8');
  assert.ok(home.includes('label: "Forecast Accuracy"'));
  assert.ok(home.includes('Historical Daily-7 reference; not a future guarantee or deployment verification'));
  assert.ok(!home.includes('detail: "Historical · Daily-7'));
  assert.ok(!home.includes('<ConfidenceGauge'));
  assert.ok(product.includes('<HistoricalIndicator product={product} horizon={chartPeriod} />'));
  assert.equal((product.match(/<HistoricalIndicator /g) ?? []).length, 1);
  assert.ok(!product.includes('label: "Confidence Level"'));
  const indicator=readFileSync('app/components/HistoricalIndicator.tsx','utf8');
  assert.ok(!indicator.includes('/api/forecast/historical-indicator'));
  assert.ok(!indicator.includes('historicalSummary'));
  assert.ok(!indicator.includes('dailyModelSummary'));
  assert.ok(indicator.includes('Historical ±₱5 hit frequency is not used as confidence'));
  assert.ok(readFileSync('app/lib/historical-indicator.ts','utf8').includes('c.model_run_id === model'));
  assert.ok(!product.includes('<ConfidenceGauge'));
  assert.ok(!product.includes('<ProductAccuracyPanel'));
  assert.ok(!product.includes('productValidationReliability(product,'));
});
