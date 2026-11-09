import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const read=p=>readFileSync(p,'utf8');
const head=p=>execFileSync('git',['show',`HEAD:foodcast/${p}`],{encoding:'utf8'});
test('translations restore HEAD presentation outside preserved confidence and horizon correctness',()=>{
 const current=read('app/lib/i18n/translations.ts');
 for(const key of ['modelAccuracy','predictionSuccess']){
 const line=s=>s.split('\n').find(l=>l.trimStart().startsWith(key+':')).trimEnd();
 assert.equal(line(current),line(head('app/lib/i18n/translations.ts')));
 }
});
test('product retains exact analysis section and all accuracy surfaces retain their source',()=>{
 const original=read('../audits/frontend_restore_preserve_analysis/backup/foodcast/app/client/Product.tsx');
 const product=read('app/client/Product.tsx');
 for(const token of ['Analysis forecast horizon','marketAnalysisForecasts(product, analysisHorizon)','data={selectedChartData}','<HistoricalIndicator product={product} horizon="daily" />']) assert.ok(product.includes(token));
 for(const p of ['app/client/Home.tsx','app/client/About.tsx','app/page.tsx']) assert.equal(read(p),read('../audits/frontend_restore_preserve_analysis/backup/foodcast/'+p));
 assert.ok(!product.includes('if (!product || historicalPreview || researchMode || rollingResearch) return;'));
 assert.ok(product.includes('predictedPrice: analysisPrice'));
 assert.ok(product.includes('[id, researchMode, chartPeriod]'));
 assert.ok(!product.includes('{useExperimental ? <p className="text-sm text-gray-600'));
 assert.ok(!product.includes('Daily model average over complete predicted daily periods.'));
 assert.ok(!product.includes('Observed source anchor: Nov 4'));
 assert.ok(!product.includes('{researchName} · origin'));
 assert.ok(product.includes('dailyAverageMode ? displayedForecasts[0]?.predicted_price ?? null'));
 assert.ok(!read('app/components/Footer.tsx').includes(' ? null : historicalAccuracy'));
});
test('unused gauge presentation is exactly HEAD again',()=>{
 assert.equal(read('app/components/ConfidenceGauge.tsx').replace(/\r\n/g,'\n'),head('app/components/ConfidenceGauge.tsx'));
});
test('explicit historical vintage prevents default daily-average substitution',()=>{
 const product=read('app/client/Product.tsx');
 assert.ok(product.includes('dailyAverageMode ? "&vintage=daily-average" : "&vintage=historical"'));
});
