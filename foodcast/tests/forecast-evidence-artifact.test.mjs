import test from 'node:test';
import assert from 'node:assert/strict';
import {loadTs} from './load-ts.mjs';
import {readFileSync} from 'node:fs';
const parser=loadTs('../app/lib/historical-performance.server.ts',{'./historical-accuracy.json':JSON.parse(readFileSync('app/lib/historical-accuracy.json','utf8'))});
const {verifiedHistoricalEvidence}=loadTs('../app/lib/forecast-evidence.server.ts',{'./historical-performance.server':parser});
test('local registry replays product/lead accuracy from hash-bound original daily saved predictions',async()=>{
 const rows=await verifiedHistoricalEvidence();assert.ok(rows.length>0);assert.ok(rows.every(r=>r.horizon==='daily'&&r.route==='incumbent_served'&&r.verified));
 const romaine=rows.find(r=>r.name==='Lettuce'&&r.variant==='Romaine'&&r.lead===null);assert.ok(romaine);assert.ok(romaine.n>0);assert.ok(Number.isFinite(romaine.forecast_accuracy_pct));
});
