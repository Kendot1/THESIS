import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {loadTs} from './load-ts.mjs';
const context={category:'Fish',name:'Tilapia',variant:'Standard',origin:'Local',unit:'kg',modelId:'incumbent',route:'model',contractId:'rolling_daily7_weekly4_monthly30_v2',horizon:'weekly',lead:null,forecastOrigin:'2026-11-09',modelOrigin:'2026-11-06',leadStart:4,leadEnd:31,targetStart:'2026-11-10',targetEnd:'2026-11-16',targetStatistic:'rolling_7day_mean'};
test('confidence API returns explicit missing evidence for complete aggregate scope and rejects incomplete scope',async()=>{
 const {GET}=loadTs('../app/api/forecast/confidence/route.ts',{'../../../lib/confidence-registry.server':{approvedConfidenceRegistry:async()=>[]}});
 const query=new URLSearchParams(Object.entries(context).map(([k,v])=>[k,String(v)]));
 let r=await GET(new Request('http://localhost/api/forecast/confidence?'+query));assert.equal(r.status,200);const body=await r.json();assert.equal(body.evidence.kind,'unavailable');assert.equal(body.context.horizon,'weekly');assert.equal(body.confidence_pct,null);assert.match(body.evidence.details,/4.*31/);
 query.delete('unit');r=await GET(new Request('http://localhost/api/forecast/confidence?'+query));assert.equal(r.status,400);
});
test('incomplete selection displays unavailable without sending a malformed request',()=>{
 let effect;
 const React={useState:()=>[null,()=>{}],useEffect:fn=>{effect=fn}};
 const evidence={resolveConfidenceEvidence:()=>({kind:'unavailable',value:null,label:'Confidence level',details:'Incomplete'})};
 const {default:Badge}=loadTs('../app/components/ForecastConfidenceBadge.tsx',{'react':React,'./ConfidenceWidget':{default:()=>null},'../lib/forecast-evidence':evidence});
 Badge({context:{...context,modelId:'',modelOrigin:'',targetStart:'',targetEnd:''}});
 assert.doesNotThrow(()=>effect(), 'incomplete selection must not reach fetch');
});

test('real Product card uses selected horizon and identity-bound confidence regardless of experimental mode',()=>{
 const source=readFileSync('app/client/Product.tsx','utf8');assert.match(source,/<ForecastConfidenceBadge/);assert.match(source,/horizon:chartPeriod/);assert.ok(!source.includes('useExperimental ? <ConfidenceWidget'));
 const badge=readFileSync('app/components/ForecastConfidenceBadge.tsx','utf8');assert.match(badge,/result\?\.key === key/);assert.match(badge,/cancelled = true/);assert.match(badge,/resolveConfidenceEvidence/);
});
