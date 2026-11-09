import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {loadTs} from './load-ts.mjs';
const load=()=>loadTs('../app/lib/daily-average.ts');
test('rejects duplicate, invalid or nonfinite days and invalid origin',()=>{const {aggregateDailyPath:f}=load();const p=Array.from({length:30},(_,i)=>({date:new Date(Date.UTC(2026,10,7+i)).toISOString().slice(0,10),prediction:i+1}));for(const v of [[...p,p[0]],p.map((r,i)=>i?r:{...r,prediction:NaN}),p.map((r,i)=>i?r:{...r,date:'2026-02-30'})])assert.throws(()=>f('2026-11-06',v));assert.throws(()=>f('2026-02-30',p));});
test('leap and year boundaries always use exactly thirty days',()=>{const {aggregateDailyPath:f}=load();for(const [origin,end] of [['2024-01-31','2024-03-01'],['2024-02-29','2024-03-30'],['2025-01-31','2025-03-02'],['2026-12-31','2027-01-30']]){const p=Array.from({length:30},(_,i)=>({date:new Date(Date.parse(origin)+86400000*(i+1)).toISOString().slice(0,10),prediction:i+1}));assert.equal(f(origin,p).at(-1).target_end,end);}});
test('normal interface has no local banner or model dropdown clutter',()=>{const s=fs.readFileSync('app/client/Product.tsx','utf8');assert.ok(!s.includes('data-testid="staging-banner"'));assert.ok(!s.includes('Analysis model (local only)'));assert.ok(!s.includes('id="analysis-model"'));});
test('complete nonflat daily path gives arithmetic weekly/monthly means and preserves first seven',()=>{
 const {aggregateDailyPath}=load();const path=Array.from({length:30},(_,i)=>({date:new Date(Date.UTC(2026,10,7+i)).toISOString().slice(0,10),prediction:i+1}));const before=JSON.stringify(path);
 const rows=aggregateDailyPath('2026-11-06',path);assert.equal(rows.length,12);assert.deepEqual(Array.from(rows.slice(0,7),r=>r.prediction),[1,2,3,4,5,6,7]);assert.deepEqual(Array.from(rows.slice(7),r=>r.prediction),[4,11,18,25,15.5]);assert.equal(JSON.stringify(path),before);
});
