import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {createRequire} from 'node:module';
const native=createRequire(import.meta.url);
import {loadTs} from './load-ts.mjs';
const m={exports:loadTs('../app/lib/local-rolling.ts')};
const root='../audits/fresh_rolling_current_20261109/';
const payload=JSON.parse(fs.readFileSync(root+'forecasts.json'));
const products=JSON.parse(fs.readFileSync(root+'products.json'));
const product=products.find(p=>p.name==='Baguio Beans');
test('fresh sealed read is real four weeks and one month, never daily or borrowed metrics',async()=>{
 const r=await m.exports.readFreshRolling(product.id);assert.equal(r.forecast_origin,'2026-11-09');assert.equal(r.metrics,null);assert.equal(r.predictions.length,5);assert.deepEqual(Array.from(r.predictions,p=>p.prediction),[126.5,126.5,126.5,126.51,126.36]);assert.equal(r.predictions.filter(p=>p.horizon==='daily').length,0);
});
test('fresh selector rejects incorrect identity, origin, missing or duplicate periods',()=>{
 const select=m.exports.selectFreshRolling;
 for(const k of ['unit','variant','name','origin','category'])assert.equal(select(payload,{...product,[k]:'WRONG'}).predictions.length,0);
 const rows=select(payload,product).predictions;
 for(const predictions of [rows.slice(1),[...rows,rows[0]],rows.map((r,i)=>i? r:{...r,target_start:'2026-11-09'})])assert.equal(select({...payload,predictions},product).predictions.length,0);
 assert.equal(select({...payload,forecast_origin:'2025-11-28'},product).predictions.length,0);
});
