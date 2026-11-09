import test from 'node:test';
import assert from 'node:assert/strict';
import {loadTs} from './load-ts.mjs';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
test('historical panel retains eligible historical ring separately from always-visible confidence',()=>{
 const Widget=loadTs('../app/components/ConfidenceWidget.tsx');
 const Panel=loadTs('../app/components/ProductAccuracyPanel.tsx',{'./ConfidenceWidget':Widget}).default;
 const html=renderToStaticMarkup(Panel({accuracy:null,evidence:{kind:'historicalaccuracy',value:91.9,label:'HISTORICAL FORECAST ACCURACY',details:'Original contract only',evidenceId:'test'}}));
 assert.match(html,/Confidence level/);assert.match(html,/Insufficient data/);assert.match(html,/HISTORICAL FORECAST ACCURACY/);assert.match(html,/91.9%/);
});
test('accuracy preview contains no hardcoded demonstration confidence',()=>{const text=readFileSync('app/accuracy-preview/AccuracyPreview.tsx','utf8');assert.ok(!text.includes('63.2'));assert.ok(!text.includes('Design example'));});
