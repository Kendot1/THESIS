import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const exports={};new Function('exports',ts.transpile(readFileSync('app/lib/historical-indicator.ts','utf8'),{module:ts.ModuleKind.CommonJS}))(exports);
const cell={series:'s',model_run_id:'m',contract:'daily7_current_local',horizon:'daily',lead:'1',route:'model',n:20,hits:20,pct:100};
test('perfect historical sample is reported with uncertainty, not fabricated certainty',()=>{const s=exports.historicalSummary(cell);assert.equal(s.pct,100);assert.ok(s.low<100);assert.ok(s.low>0);assert.equal(exports.historicalSummary({...cell,n:19}),null);});
test('daily model summary requires every supported lead and pools hits, not percentages',()=>{
 const cells=Array.from({length:7},(_,i)=>({...cell,lead:String(i+1),n:i===0?40:20,hits:i===0?20:20,pct:i===0?50:100}));
 const s=exports.dailyModelSummary(cells,'s','m');
 assert.equal(s.n,160);assert.equal(s.hits,140);assert.equal(s.pct,87.5);
 assert.equal(exports.dailyModelSummary(cells.slice(1),'s','m'),null);
 assert.equal(exports.dailyModelSummary([...cells,cells[0]],'s','m'),null);
 assert.equal(exports.dailyModelSummary(cells,'s','other'),null);
 assert.equal(exports.dailyModelSummary(cells.map(c=>({...c,n:19,hits:19})),'s','m'),null);
});
test('selection isolates model, contract, horizon and lead',()=>{assert.equal(exports.matchingHistoricalCells([cell],'s','m','daily',1).length,1);for(const [model,horizon,lead] of [['wrong','daily',1],['m','weekly',1],['m','daily',2]])assert.equal(exports.matchingHistoricalCells([cell],'s',model,horizon,lead).length,0);});
