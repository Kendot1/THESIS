import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './load-ts.mjs';
const data=loadTs('../app/lib/data.ts');
const {marketAnalysisForecasts}=loadTs('../app/lib/market-analysis.ts',{'./data':data});
test('published 7/4/1 payload displays persisted weekly and monthly means without 30 daily rows',()=>{
 const origin='2026-11-10';
 const periods=data.forecastTargetDate;
 const date=n=>new Date(Date.parse(origin+'T00:00:00Z')+n*86400000).toISOString().slice(0,10);
 const make=(h,s,e,step)=>({horizon:h,date:date(e),target_period_start:date(s),target_period_end:date(e),forecast_step:step,actual:null,predicted:100+step,name:'',covered_days:e-s+1,period_days:e-s+1});
 const weeks=Array.from({length:4},(_,i)=>make('weekly',i*7+1,i*7+7,i+1));
 const month=make('monthly',0,29,1);
 const p={forecastSource:'model',forecastOriginDate:origin,forecastData:[...Array.from({length:7},(_,i)=>make('daily',i+1,i+1,i+1)),...weeks,month]};
 assert.equal(marketAnalysisForecasts(p,'weekly').length,4);
 assert.equal(marketAnalysisForecasts(p,'monthly')[0]?.predicted,101);
});
