import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { loadTs } from './load-ts.mjs';

test('test news source requires both dev mode and explicit read-only flag', () => {
 const { localNewsEnabled, TEST_NEWS_URL } = loadTs('../app/lib/news-source.ts');
 assert.equal(TEST_NEWS_URL, 'https://zhwhnnxbodzrklhgsurn.supabase.co');
 assert.equal(localNewsEnabled({NODE_ENV:'production',FOODCAST_LOCAL_READ_ONLY:'1'}), false);
 assert.equal(localNewsEnabled({NODE_ENV:'development'}), false);
 assert.equal(localNewsEnabled({NODE_ENV:'development',FOODCAST_LOCAL_READ_ONLY:'1'}), true);
});

test('news bridge is GET-only, anon-only and cannot redirect to arbitrary projects', () => {
 const route = fs.readFileSync(new URL('../app/api/local-news/route.ts', import.meta.url), 'utf8');
 assert.match(route, /localNewsEnabled\(process.env\)/);
 assert.match(route, /name === 'anon'/);
 assert.doesNotMatch(route, /service_role|export async function (POST|PUT|PATCH|DELETE)/);
 assert.match(route, /TEST_NEWS_URL/);
});

test('timestamp news dates display in the NCR publication timezone without inventing missing dates', () => {
 const { formatNewsPublicationDate } = loadTs('../app/lib/data.ts');
 assert.equal(formatNewsPublicationDate('2026-11-08T16:00:00+00:00','2026-11-09','timestamp'), 'Nov 9, 2026');
 assert.equal(formatNewsPublicationDate(null,null,'unknown'), 'Publication date unavailable');
});

test('production and unflagged development route return 404 before credential or network access', async () => {
 const source = fs.readFileSync(new URL('../app/api/local-news/route.ts', import.meta.url), 'utf8');
 for (const env of [{NODE_ENV:'production',FOODCAST_LOCAL_READ_ONLY:'1'}, {NODE_ENV:'development'}]) {
  let accessed = false;
  const module = {exports:{}};
  const require = id => id.includes('news-source') ? loadTs('../app/lib/news-source.ts')
    : id === 'node:util' ? {promisify:()=>()=>{accessed=true; throw Error('must not execute');}}
    : {execFile:()=>{accessed=true;}};
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,
    {module,exports:module.exports,require,process:{env},Response,URL,fetch:()=>{accessed=true; throw Error('must not fetch');}});
  const response = await module.exports.GET(new Request('http://localhost/api/local-news'));
  assert.equal(response.status,404);
  assert.equal(accessed,false);
  assert.deepEqual(await response.json(),{error:'Not found'});
 }
});
