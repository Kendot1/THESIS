import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {loadTs} from './load-ts.mjs';
const data = loadTs('../app/lib/data.ts');
const periods=loadTs('../app/lib/rolling-periods.ts');
const fixture=JSON.parse(fs.readFileSync('../contracts/rolling-periods.json'));
test('monthly selection is exactly thirty days across year and leap boundaries',()=>{
 for(const c of fixture.cases) assert.equal(data.forecastTargetDate(c.origin,'monthly'),c.monthly[0][1]);
});
test('missing required dates are unavailable per period, never partial means',()=>{
 const {aggregateDailyPath}=loadTs('../app/lib/daily-average.ts');
 const path=Array.from({length:30},(_,i)=>({date:new Date(Date.UTC(2026,10,10+i)).toISOString().slice(0,10),prediction:i+1}));
 const rows=aggregateDailyPath('2026-11-09',path.filter(r=>r.date!=='2026-12-09'));
 assert.equal(rows.at(-1).prediction,null);assert.equal(rows.at(-1).unavailable,true);assert.match(rows.at(-1).unavailable_reason,/2026-12-09/);
 assert.equal(rows.filter(r=>r.horizon==='weekly'&&!r.unavailable).length,4);
});
test('shared fixture, Manila timezone, exact labels, means and 28/30 coverage',()=>{
 assert.equal(periods.manilaToday(new Date('2026-11-08T17:30:00Z')),'2026-11-09');
 for(const c of fixture.cases){const p=periods.rollingPeriods(c.origin);for(const h of ['weekly','monthly'])if(c[h])assert.deepEqual(Array.from(p[h],r=>[r.target_start,r.target_end]),c[h]);}
 const p=periods.rollingPeriods('2026-11-09');assert.equal(p.daily.length,7);assert.equal(p.weekly.at(-1).target_end,'2026-12-07');assert.equal(p.monthly[0].period_days,30);
 assert.equal(periods.rollingPeriodLabel(p.monthly[0].target_start,p.monthly[0].target_end,'monthly'),'Nov 10–Dec 9');
 const path=Array.from({length:30},(_,i)=>({date:new Date(Date.UTC(2026,10,10+i)).toISOString().slice(0,10),prediction:i+1}));
 const rows=loadTs('../app/lib/daily-average.ts').aggregateDailyPath('2026-11-09',path);
 assert.deepEqual(Array.from(rows.slice(7),r=>r.prediction),[4,11,18,25,15.5]);
});
test('open rolling local forecasts never borrow historical accuracy percent',()=>{
 const hook=loadTs('../app/lib/use-historical-accuracy.ts',{swr:{default:()=>({data:{historical_forecast_accuracy_pct:99}}),__esModule:true}});
 const before=process.env.NEXT_PUBLIC_FOODCAST_LOCAL_MODEL;process.env.NEXT_PUBLIC_FOODCAST_LOCAL_MODEL='current-hybrid';process.env.NODE_ENV='development';
 try{assert.equal(hook.useHistoricalAccuracy(),null);}finally{if(before==null)delete process.env.NEXT_PUBLIC_FOODCAST_LOCAL_MODEL;else process.env.NEXT_PUBLIC_FOODCAST_LOCAL_MODEL=before;}
});
