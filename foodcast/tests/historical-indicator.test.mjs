import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url);
test('actual historical API verifies saved bytes and returns independently calculated cells',async()=>{
 const src=readFileSync('app/api/forecast/historical-indicator/route.ts','utf8');
 const code=ts.transpile(src,{module:ts.ModuleKind.CommonJS,esModuleInterop:true,target:ts.ScriptTarget.ES2022});
 const exports={};new Function('exports','require',code)(exports,require);
 const response=await exports.GET();const data=await response.json();
 assert.equal(data.cells.length,1161);
 for(const c of data.cells){if(c.pct!==null){assert.ok(c.n>=20);assert.equal(c.pct,100*c.hits/c.n);}assert.equal(c.classification,'DEVELOPMENT_REUSED');}
 assert.ok(data.cells.filter(c=>c.horizon==='monthly').every(c=>c.pct===null));
});
