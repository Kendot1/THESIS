import test from 'node:test';
import assert from 'node:assert/strict';
import { harness } from './predict-current-data.test.mjs';
const item = {product:{id:'a'},forecast_origin:'2026-11-06',predictions:[
 {horizon:'daily',lead:1,target_start:'2026-11-07',target_end:'2026-11-07',forecast_origin:'2026-11-06',prediction:126.06},
 {horizon:'weekly',lead:1,target_start:'2026-11-07',target_end:'2026-11-13',forecast_origin:'2026-11-06',prediction:125.91142857142859},
 {horizon:'monthly',lead:1,target_start:'2026-11-07',target_end:'2026-12-06',forecast_origin:'2026-11-06',prediction:126.96166666666663}]};
test('catalog card forecast uses the same selected period output as the featured forecast',async()=>{
 const h=harness();h.render();
 const cards=()=>h.nodes().filter(n=>n.props?.variants);
 assert.equal(cards()[0].props.variants[0].predictedPrice,null,'must not flash legacy price while loading');
 const index=h.calls.findIndex(c=>c.url.includes('catalog=1'));assert.ok(index>=0,'one batch catalog request');
 await h.resolve(index,{items:[item]});
 assert.equal(cards()[0].props.variants[0].predictedPrice,126.06);
});
