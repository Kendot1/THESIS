import test from 'node:test';
import assert from 'node:assert/strict';
import {loadTs} from './load-ts.mjs';
import {renderToStaticMarkup} from 'react-dom/server';
const lib=loadTs('../app/lib/forecast-evidence.ts');
const context={category:'Fish',name:'Tilapia',variant:'Standard',origin:'Local',unit:'kg',modelId:'incumbent',route:'model',contractId:'rolling_daily7_weekly4_monthly30_v2',horizon:'daily',lead:null,forecastOrigin:'2026-11-09',modelOrigin:'2026-11-06',leadStart:4,leadEnd:10,targetStart:'2026-11-10',targetEnd:'2026-11-10',targetStatistic:'daily_price'};
const approved={...context,evidenceId:'test-evidence',verified:true,approved:true,value:18.2,classification:'Low',measures:'Approved PHP5 probability',approvalReceipt:'test-only-independent-receipt',provenance:'test-only-hash-bound-source',method:'validated_regression_probability',rangeDefinition:'test-only',calculationProvenance:'test-only'};
test('confidence-only resolver never substitutes historical accuracy and explains rolling bridge',()=>{
 const r=lib.resolveConfidenceEvidence(context,[]);
 assert.equal(r.value,null);assert.equal(r.label,'Confidence level');
 assert.match(r.details,/rolling.*7|daily7/i);assert.match(r.details,/4.*10/);assert.match(r.details,/2026-11-09/);
});
test('approved existing classifications and endpoint percentages survive exact admission',()=>{
 for(const value of [0,18.2,100]) {const r=lib.resolveConfidenceEvidence(context,[{...approved,value}]);assert.equal(r.value,value);assert.ok(!('classification' in r));}
 for(const key of Object.keys(context)) assert.equal(lib.resolveConfidenceEvidence({...context,[key]:key==='lead'?1:'wrong'},[approved]).value,null,key);
 for(const value of [null,undefined,NaN,Infinity,-1,101])assert.equal(lib.resolveConfidenceEvidence(context,[{...approved,value}]).value,null);
 for(const field of ['approvalReceipt','provenance','measures'])assert.equal(lib.resolveConfidenceEvidence(context,[{...approved,[field]:''}]).value,null);

});
test('confidence widget rejects historical substitution and always has explicit visible heading',()=>{
 const Widget=loadTs('../app/components/ConfidenceWidget.tsx').default;
 const html=renderToStaticMarkup(Widget({evidence:{kind:'historicalaccuracy',value:91.9,label:'HISTORICAL FORECAST ACCURACY',details:'Not confidence',evidenceId:'archived'}}));
 assert.match(html,/Confidence level/);assert.match(html,/Insufficient data/);assert.ok(!html.includes('91.9%'));assert.match(html,/—/);
 const low=renderToStaticMarkup(Widget({evidence:lib.resolveConfidenceEvidence(context,[approved])}));assert.match(low,/18\.2%/);assert.ok(!low.includes('#dc2626'));
});
