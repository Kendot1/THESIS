import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {loadTs} from './load-ts.mjs';
const dataModule = loadTs('../app/lib/data.ts');
const selectorModule = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../app/lib/market-analysis.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, { module: selectorModule, exports: selectorModule.exports, require: () => dataModule });
const { marketAnalysisForecasts } = selectorModule.exports;
const load = (file, deps = {}) => {
  const module = { exports: {} };
  const require = id => deps[id] ?? {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText, { module, exports: module.exports, require, process: {env:{}} });
  return module.exports;
};
const dataHelpers = dataModule;
function chartSeries(data, period, forecastOriginDate, view) {
  const memos = [], callbacks = [];
  const react = { useRef: () => ({current:view?.chart ?? null}), useEffect: () => {}, useCallback: fn => {callbacks.push(fn);return fn;}, useMemo: fn => { const v = fn(); memos.push(v); return v; } };
  const chart = load('../app/components/ForecastChart.tsx', {
    react, 'react/jsx-runtime': { jsx: () => null, jsxs: () => null },
    '../lib/data': dataHelpers, '../lib/market-analysis': { marketAnalysisForecasts },
    '../lib/i18n/LanguageContext': { useLanguage: () => ({t: x => x}) },
  });
  chart.default({data,period,forecastOriginDate});
  if (view) callbacks.forEach(fn=>fn());
  return memos.find(v => v?.predictedData);
}
const point = (start,end,horizon,predicted=100) => ({date:end,name:'Saved',actual:null,predicted,horizon,target_period_start:start,target_period_end:end});
test('November 9 chart and analysis select the saved rolling month Nov10-Dec9, not calendar December', () => {
  const rolling = point('2026-11-10','2026-12-09','monthly',106.47);
  const data = [point('2026-11-01','2026-11-30','monthly'), rolling, point('2026-12-01','2026-12-31','monthly')];
  assert.deepEqual(Array.from(chartSeries(data,'monthly','2026-11-09').predictedData,p=>p.time),['2026-12-09']);
  const expected = marketAnalysisForecasts({forecastData:data,forecastOriginDate:'2026-11-09',forecastSource:'model'},'monthly');
  assert.equal(expected[0], rolling);
  assert.equal(chartSeries(data,'monthly','2026-11-09').predictedData[0].value,106.47);
});
test('November 9 weekly chart and analysis preserve four exact saved rolling windows and prices', () => {
 const data = [['2026-11-10','2026-11-16'],['2026-11-17','2026-11-23'],['2026-11-24','2026-11-30'],['2026-12-01','2026-12-07']]
   .map(([start,end],i)=>point(start,end,'weekly',101+i));
 const series=chartSeries([...data].reverse(),'weekly','2026-11-09');
 assert.deepEqual(Array.from(series.predictedData,p=>p.time),['2026-11-16','2026-11-23','2026-11-30','2026-12-07']);
 assert.deepEqual(Array.from(series.predictedData,p=>p.value),[101,102,103,104]);
 const analysis=marketAnalysisForecasts({forecastData:data,forecastOriginDate:'2026-11-09',forecastSource:'model'},'weekly');
 assert.deepEqual(Array.from(analysis,p=>p.predicted),[101,102,103,104]);
});
test('daily chart uses seven targets, not the legacy fourteen or thirty', () => {
 const data = Array.from({length:14},(_,i)=>point(`2026-11-${String(6+i).padStart(2,'0')}`,`2026-11-${String(6+i).padStart(2,'0')}`,'daily'));
 assert.equal(chartSeries(data,'daily','2026-11-05').predictedData.length,7);
});
test('historical research chart never uses current November actuals as a future timeline or anchor',()=>{
 const data = [point('2026-02-01','2026-02-28','monthly',90.18),{...point('2026-11-01','2026-11-30','monthly'),actual:109.06,predicted:null}];
 const series=chartSeries(data,'monthly','2026-01-01');
 assert.equal(series.actualData.length,0);
 // Calendar-only records are unavailable on the active rolling path.
 assert.deepEqual(Array.from(series.predictedData,p=>p.time),[]);
 const historical = marketAnalysisForecasts({forecastData:data,forecastOriginDate:'2026-01-01',forecastSource:'model'}, 'monthly', 'calendar_research');
 assert.deepEqual(Array.from(historical,p=>p.date),['2026-02-28']);
});
test('weekly and monthly charts use daily observations, never closed-period means as the live price', () => {
 const origin = '2026-11-09';
 const observed = {date:'2026-11-04',name:'Observed',horizon:'daily',actual:125.93,predicted:null};
 const later = {...observed,date:'2026-11-10',actual:999};
 for (const horizon of ['weekly','monthly']) {
   const staleMean = {...observed,horizon,date:'2026-10-31',actual:141.39};
   const targets = horizon === 'monthly'
     ? [point('2026-11-10','2026-12-09','monthly',126.71)]
     : [['2026-11-10','2026-11-16'],['2026-11-17','2026-11-23'],['2026-11-24','2026-11-30'],['2026-12-01','2026-12-07']].map(([s,e])=>point(s,e,'weekly',126));
   const series = chartSeries([observed,later,staleMean,...targets],horizon,origin);
   assert.deepEqual(Array.from(series.actualData,p=>p.value),[125.93]);
   assert.equal(series.predictedData[0].value,125.93);
   assert.equal(series.predictedData[0].time,'2026-11-04');
   assert.equal(series.predictedData.length,targets.length+1);
 }
});
test('actual chart series aggregate observed daily history, retain a real shared anchor and preserve saved forecasts', () => {
 const daily = [];
 for (let date = new Date('2026-04-01T00:00:00Z'), i=0; date <= new Date('2026-11-06T00:00:00Z'); date.setUTCDate(date.getUTCDate()+1), i++) {
   daily.push({date:date.toISOString().slice(0,10),name:'Observed',horizon:'daily',actual:i+10,predicted:null});
 }
 daily.at(-1).actual=125.93;
 const saved = [
   ...Array.from({length:7},(_,i)=>point(`2026-11-${String(7+i).padStart(2,'0')}`,`2026-11-${String(7+i).padStart(2,'0')}`,'daily',130+i)),
   ...[['2026-11-07','2026-11-13'],['2026-11-14','2026-11-20'],['2026-11-21','2026-11-27'],['2026-11-28','2026-12-04']].map(([s,e],i)=>point(s,e,'weekly',140+i)),
   point('2026-11-07','2026-12-06','monthly',150),
 ];
 const input=[...daily,{...daily[0],date:'2026-11-07',actual:99999},...saved];
 const series=Object.fromEntries(['daily','weekly','monthly'].map(h=>[h,chartSeries(input,h,'2026-11-06')]));
 assert.equal(series.daily.actualData.length,daily.length);
 assert.ok(series.weekly.actualData.length>9);
 assert.ok(series.monthly.actualData.length>7);
 for (const [h,count] of [['daily',7],['weekly',4],['monthly',1]]) {
   const actual=Array.from(series[h].actualData);
   assert.equal(actual.at(-1).time,'2026-11-06');
   assert.equal(actual.at(-1).value,125.93);
   assert.equal(new Set(actual.map(p=>p.time)).size,actual.length);
   assert.ok(actual.every(p=>p.time<='2026-11-06'));
   assert.equal(series[h].predictedData[0].value,125.93);
   assert.deepEqual(Array.from(series[h].predictedData).slice(1).map(p=>p.value),saved.filter(p=>p.horizon===h).map(p=>p.predicted));
   assert.equal(series[h].forecastPoints.length,count);
 }
 const mean=(start,end)=>{const rows=daily.filter(p=>p.date>=start&&p.date<=end);return rows.reduce((sum,p)=>sum+p.actual,0)/rows.length;};
 assert.equal(series.weekly.actualData.at(-2).time,'2026-11-01');
 assert.equal(series.weekly.actualData.at(-2).value,mean('2026-10-26','2026-11-01'));
 assert.equal(series.monthly.actualData.at(-2).time,'2026-10-31');
 assert.equal(series.monthly.actualData.at(-2).value,mean('2026-10-01','2026-10-31'));
 assert.equal(series.daily.actualData[0].time,'2026-04-01');
});

test('visible chart range includes aggregate history and target, with truthful cadence ticks',()=>{
 for (const [h,label] of [['daily','6'],['weekly','Nov 6'],['monthly','Nov']]) {
   let options,range;
   const chart={applyOptions:o=>{options=o;},timeScale:()=>({setVisibleRange:r=>{range=r;},fitContent:()=>assert.fail('unexpected fallback')})};
   const observed=[{date:'2026-10-01',actual:90,horizon:'daily'},{date:'2026-10-31',actual:110,horizon:'daily'},{date:'2026-11-06',actual:125.93,horizon:'daily'}];
   const targets=h==='monthly'?[point('2026-11-07','2026-12-06',h)]:h==='weekly'
     ? [['2026-11-07','2026-11-13'],['2026-11-14','2026-11-20'],['2026-11-21','2026-11-27'],['2026-11-28','2026-12-04']].map(([s,e])=>point(s,e,h))
     : Array.from({length:7},(_,i)=>{const d=`2026-11-${String(7+i).padStart(2,'0')}`;return point(d,d,h);});
   const series=chartSeries([...observed,...targets],h,'2026-11-06',{chart});
   assert.equal(range.from,series.actualData[0].time);
   assert.equal(range.to,series.predictedData.at(-1).time);
   assert.equal(options.timeScale.tickMarkFormatter('2026-11-06'),label);
 }
});
test('boundary anchors and sparse observations never fabricate daily prices or duplicate period times',()=>{
 const data=[{date:'2026-01-01',actual:100},{date:'2026-01-03',actual:120},{date:'2026-01-31',actual:125.93},{date:'2026-02-01',actual:999}];
 const monthly=chartSeries(data,'monthly','2026-01-31');
 assert.deepEqual(Array.from(monthly.actualData,p=>[p.time,p.value]),[['2026-01-31',125.93]]);
 const weekly=chartSeries(data,'weekly','2026-01-31');
 assert.equal(weekly.actualData[0].time,'2026-01-04');
 assert.equal(weekly.actualData[0].value,110);
 const daily=chartSeries(data,'daily','2026-01-31');
 assert.equal(daily.actualData.length,3);
});
test('monthly analysis label shows the exact averaged date range',()=>{
 const source=fs.readFileSync(new URL('../app/client/Product.tsx',import.meta.url),'utf8');
 const {rollingPeriodLabel:label}=loadTs('../app/lib/rolling-periods.ts');
 assert.equal(label('2026-11-10','2026-12-09','monthly','en'),'Nov 10–Dec 9');
 assert.equal(label('2026-11-10','2026-11-16','weekly','en'),'Week Nov 10–Nov 16');
 assert.match(source,/periodLabel: rollingPeriodLabel\(row.target_start, row.target_end/);
 assert.match(source,/forecastExplanation\([^;]*row\.target_start, row\.target_end/);
});
test('both visible horizon controls share one state instead of silently diverging',()=>{
 const source=fs.readFileSync(new URL('../app/client/Product.tsx',import.meta.url),'utf8');
 assert.doesNotMatch(source,/\[analysisHorizon, setAnalysisHorizon\] = useState/);
 assert.match(source,/const analysisHorizon = chartPeriod/);
 assert.match(source,/setAnalysisHorizon = setChartPeriod/);
});
