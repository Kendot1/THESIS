import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {loadTs} from './load-ts.mjs';
const load=()=>loadTs('../app/lib/local-rolling.ts');
import {createRequire} from 'node:module';
const requireNative=createRequire(import.meta.url);
test('sealed rolling source: exact identity, complete 7/4/1, null metrics and no actuals',async()=>{
 const {readLocalRolling}=load();
 const products=JSON.parse(fs.readFileSync(new URL('../../audits/local_rolling_hybrid_integration/products.json',import.meta.url)));
 const report=JSON.parse(fs.readFileSync(new URL('../../audits/local_rolling_hybrid_integration/manifest.json',import.meta.url)));
 const result=await readLocalRolling(products.find(p=>p.id===report.example_product_id).id);
 assert.equal(result.forecast_origin,report.forecast_origin);
 for(const [h,n] of [['daily',7],['weekly',4],['monthly',1]]) assert.equal(result.predictions.filter(p=>p.horizon===h).length,n);
 assert.equal(result.metrics,null);
 for(const p of result.predictions){assert.equal(p.confidence_score,null);assert.equal(p.actual,undefined);assert.equal(p.prediction,Number(p.prediction));assert.ok(p.model);}
 const absent=await readLocalRolling('00000000-0000-0000-0000-000000000000');
 assert.equal(absent.predictions.length,0);assert.ok(absent.unavailable_reason);
});
test('full identity guard rejects changed unit, variant, origin and missing/duplicate periods',()=>{
 const {selectRolling}=load();
 const payload=JSON.parse(fs.readFileSync(new URL('../../audits/local_rolling_hybrid_integration/forecasts.json',import.meta.url)));
 const products=JSON.parse(fs.readFileSync(new URL('../../audits/local_rolling_hybrid_integration/products.json',import.meta.url)));
 const first=payload.predictions[0].product_series;
 const product=products.find(p=>p.category===first.product_category && p.name===first.product_name && p.variant===first.product_variant && p.origin===first.origin && p.unit===first.unit);
 assert.equal(selectRolling(payload,product).predictions.length,12);
 for(const field of ['unit','variant','origin','category','name']) assert.equal(selectRolling(payload,{...product,[field]:'WRONG'}).predictions.length,0);
 const selected=selectRolling(payload,product).predictions;
 for(const predictions of [selected.slice(1),[...selected,selected[0]],selected.map((p,i)=>i===0?{...p,target_start:'2025-01-01'}:p)]) assert.equal(selectRolling({...payload,predictions},product).predictions.length,0);
});
