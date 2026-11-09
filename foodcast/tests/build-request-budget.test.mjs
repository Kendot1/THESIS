import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import http from 'node:http';
import https from 'node:https';
import test from 'node:test';

test('dynamic product/tag routes preserve hourly ISR without fetching all data to enumerate build paths', async () => {
  for (const file of ['Product/[id]/page.tsx', 'tags/[id]/page.tsx']) {
    const source = fs.readFileSync(new URL(`../app/${file}`, import.meta.url), 'utf8');
    const match = source.match(/export async function generateStaticParams\(\) \{([\s\S]*?)\n\}/);
    assert.ok(match);
    assert.match(match[1], /return \[\]/);
    assert.doesNotMatch(match[1], /await fetch/);
    assert.match(source, /revalidate = 3600/);
  }
});

test('server request aborts an upstream which never responds', async () => {
  const source = fs.readFileSync(new URL('../app/lib/data.ts', import.meta.url), 'utf8');
  const start = source.indexOf('async function nativeServerFetch(');
  const end = source.indexOf('\nasync function fetchFromNetwork', start);
  const code = ts.transpileModule(source.slice(start, end), {compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText;
  const context = {getServerBuiltin: name => name === 'https' ? https : http, Buffer, URL, setTimeout, clearTimeout};
  vm.createContext(context);
  vm.runInContext(code, context);
  const server = http.createServer(() => {});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    await assert.rejects(context.nativeServerFetch(`http://127.0.0.1:${server.address().port}`, {}, 50), /deadline|timeout/i);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
