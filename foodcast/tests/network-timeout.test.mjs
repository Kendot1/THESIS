import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import test from 'node:test';
import ts from 'typescript';
import vm from 'node:vm';
import { createRequire } from 'node:module';

test('server requests abort stalled upstream connections', async () => {
  const server = http.createServer(() => {});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const source = fs.readFileSync(new URL('../app/lib/data.ts', import.meta.url), 'utf8') + '\nexport { nativeServerFetch };';
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
    const exports = {};
    const nativeRequire = createRequire(import.meta.url);
    vm.runInNewContext(code, { exports, require: name => name.startsWith('.') ? {} : nativeRequire(name), process, console, Buffer, URL, URLSearchParams, setTimeout, clearTimeout });
    const promise = exports.nativeServerFetch(`http://127.0.0.1:${server.address().port}/`, {}, 50);
    await assert.rejects(Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error('test deadline exceeded')), 500))]), /timed out/);
  } finally { server.closeAllConnections(); server.close(); }
});
