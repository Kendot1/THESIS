import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const load = (file, deps = {}, globals = {}) => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText,
    { module, exports: module.exports, process: {env:{}}, require: id => deps[id] ?? {}, ...globals });
  return module.exports;
};
import {loadTs} from './load-ts.mjs';
const data = loadTs('../app/lib/data.ts');
const adapter = load('../app/lib/local-model.ts');
const point = (horizon, start, end, predicted) => ({horizon,date:end,name:end,target_period_start:start,target_period_end:end,actual:null,predicted});
const daily = Array.from({length:7},(_,i)=>point('daily',`2026-11-${String(i+7).padStart(2,'0')}`,`2026-11-${String(i+7).padStart(2,'0')}`,120+i));
const product = id => ({id,name:id,variant:'Standard',category:'Vegetables',origin:'Local',unit:'kg',image:'/test.png',sentiment:'Bullish',currentPrice:100,predictedPrice:130,forecastSource:'model',forecastOriginDate:'2026-11-06',forecastData:[{date:'2026-11-06',actual:100,predicted:999,horizon:'daily'}, {date:'2026-10-31',actual:777,predicted:null,horizon:'weekly'},...daily]});
const payload = (id, price=140) => ({product:{id},forecast_origin:'2026-11-06',predictions:[
  ...[['2026-11-07','2026-11-13'],['2026-11-14','2026-11-20'],['2026-11-21','2026-11-27'],['2026-11-28','2026-12-04']].map(([target_start,target_end],i)=>({horizon:'weekly',target_start,target_end,forecast_origin:'2026-11-06',lead:i+1,prediction:price+i})),
  {horizon:'monthly',target_start:'2026-11-07',target_end:'2026-12-06',forecast_origin:'2026-11-06',lead:1,prediction:price+10},
]});
export function harness(mode='current-hybrid', environment='development') {
  let cursor=0, root, products=[product('a'),product('b')];
  const slots=[], effects=[], pending=[], calls=[], historyPending=[];
  const jsx=(type,props)=>({type,props:props??{}});
  const react={Suspense:'suspense',useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useRef(v){const i=cursor++;return slots[i]??(slots[i]={current:v});},useMemo:fn=>fn(),useDeferredValue:v=>v,useEffect(fn,deps){const i=cursor++;const prior=slots[i];if(!prior||deps.some((v,j)=>v!==prior.deps[j])){effects.push(()=>{prior?.cleanup?.();slots[i]={deps,cleanup:fn()};});}}};
  const ForecastChart='ForecastChart';
  const component=load('../app/client/Predict.tsx',{
    react,'react/jsx-runtime':{jsx,jsxs:jsx},'next/navigation':{useSearchParams:()=>new URLSearchParams()},'next/dynamic':()=>ForecastChart,
    '../lib/data':{...data,fetchProductPriceHistory:p=>new Promise(resolve=>historyPending.push({id:p.id,resolve})),fetchCategories:()=>Promise.resolve(['All'])},'../lib/local-model':adapter,
    '../lib/hooks':{useProducts:()=>({data:products,isLoading:false}),useNews:()=>({data:[]}),useTrendingInteractions:()=>({data:{}})},
    '../lib/i18n/LanguageContext':{useLanguage:()=>({t:v=>v})},'../lib/tags':{getInheritedTags:()=>[]},'../../lib/idCipher':{encryptId:v=>v},
  },{process:{env:{NODE_ENV:environment,NEXT_PUBLIC_FOODCAST_LOCAL_MODEL:mode}},URLSearchParams,window:{innerWidth:1200,addEventListener(){},removeEventListener(){}},document:{addEventListener(){},removeEventListener(){}},setInterval:()=>1,clearInterval(){},fetch:(url,options)=>{calls.push({url,options});return new Promise(resolve=>pending.push(resolve));}}).default;
  const inner=component({initialProducts:products}).props.children.type;
  function render(){cursor=0;root=inner({initialProducts:products});while(effects.length)effects.shift()();return root;}
  function nodes(node=root){if(Array.isArray(node))return node.flatMap(n=>nodes(n));if(!node||typeof node!=='object')return [];return [node,...nodes(node.props?.children ?? null)];}
  return {render,calls,nodes,historyPending,resolveHistory:async(i,points)=>{historyPending[i].resolve(points);await new Promise(r=>setImmediate(r));render();},chart:()=>nodes().find(n=>n.type===ForecastChart).props,
    click:label=>{nodes().find(n=>n.type==='button'&&n.props.children===label).props.onClick();render();},
    next:()=>{nodes().find(n=>n.props['aria-label']==='Go to featured item 2').props.onClick();render();},
    resolve:async(index,result,ok=true)=>{pending[index]({ok,json:async()=>result});await new Promise(r=>setImmediate(r));render();},
    text:()=>nodes().flatMap(n=>Array.isArray(n.props.children)?n.props.children:[n.props.children]).filter(v=>typeof v==='string').join(' ')};
}
test('all horizons receive one saved issue-origin daily path with matching summary',async()=>{
  const h=harness();h.render();assert.equal(h.calls.length,1);assert.equal(h.chart().forecastOriginDate,undefined);
  h.click('weekly');assert.equal(h.calls.length,1);assert.match(h.calls[0].url,/productId=a&vintage=daily-average/);
  await h.resolve(0,payload('a'));
  assert.equal(h.chart().forecastOriginDate,'2026-11-06');
  assert.equal(data.forecastHorizonPoints(h.chart().data,h.chart().forecastOriginDate,'weekly').length,4);
  assert.match(h.text(),/₱140.00/);assert.match(h.text(),/40.0/);
  assert.equal(h.chart().data.filter(p=>p.actual!=null).length,1);
  assert.equal(h.chart().data.find(p=>p.actual!=null).predicted,null);
  h.click('monthly');assert.equal(data.forecastHorizonPoints(h.chart().data,h.chart().forecastOriginDate,'monthly').length,1);
  assert.match(h.text(),/₱150.00/);assert.match(h.text(),/50.0/);
  h.click('daily');assert.equal(h.chart().data.filter(p=>p.predicted===120).length,0);
});
test('switching featured products clears previous rows and ignores late responses',async()=>{
 const h=harness();h.render();h.click('weekly');h.next();
 assert.equal(h.chart().data.filter(p=>p.predicted!=null).length,0);
 assert.match(h.calls[1].url,/productId=b&vintage=daily-average/);
 await h.resolve(1,payload('b',210));assert.match(h.text(),/₱210.00/);
 await h.resolve(0,payload('a',140));assert.match(h.text(),/₱210.00/);
 assert.ok(!h.chart().data.some(p=>p.predicted===140));
});
test('loading and unavailable API stay missing, with no daily or placeholder substitution',async()=>{
 const h=harness();h.render();h.click('monthly');
 assert.equal(h.chart().data.filter(p=>p.predicted!=null).length,0);
 await h.resolve(0,{...payload('a'),predictions:[]});
 assert.equal(h.chart().data.filter(p=>p.predicted!=null).length,0);
 assert.doesNotMatch(h.text(),/₱120.00|₱130.00/);
});
test('all fetched daily history reaches each featured horizon with identity and race protection',async()=>{
 const h=harness();h.render();assert.equal(h.historyPending.length,1);
 const old={date:'2020-01-01',horizon:'daily',actual:80,predicted:null};
 await h.resolveHistory(0,[old]);assert.ok(h.chart().data.some(p=>p.date==='2020-01-01'));
 h.click('weekly');assert.ok(h.chart().data.some(p=>p.date==='2020-01-01'));
 h.next();assert.ok(!h.chart().data.some(p=>p.date==='2020-01-01'));
 await h.resolveHistory(1,[{...old,date:'2021-01-01'}]);
 assert.ok(h.chart().data.some(p=>p.date==='2021-01-01'));
});
test('local summary compares with the chart origin-known observation, not a later live catalog price',async()=>{
 const h=harness();h.render();
 await h.resolveHistory(0,[{date:'2026-11-06',horizon:'daily',actual:125,predicted:null},{date:'2026-11-10',horizon:'daily',actual:999,predicted:null}]);
 await h.resolve(0,payload('a',140));h.click('weekly');
 assert.match(h.text(),/12.0/);
 assert.doesNotMatch(h.text(),/▲\s+40\.0\s*%/);
});
test('Product explanation uses the same origin-known daily anchor as its chart',()=>{
 const source=fs.readFileSync(new URL('../app/client/Product.tsx',import.meta.url),'utf8');
 assert.match(source,/dailyAverageMode \? researchObservedAnchor : null/);
 assert.match(source,/point\.date <= researchOrigin/);
});
test('production and unflagged development never request local models',()=>{
 for(const [mode,env] of [['current-hybrid','production'],['','development']]){
  const h=harness(mode,env);h.render();h.click('weekly');assert.equal(h.calls.length,0);
 }
});
