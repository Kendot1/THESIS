import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../supabase/functions/foodcast/request-deadline.ts', import.meta.url), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const exports = {};
vm.runInNewContext(output, { exports, setTimeout, clearTimeout });
const { withRequestDeadline, RequestDeadlineError } = exports;

test('deadline resolves a successful request and clears its timer', async () => {
  let cleared = false;
  const result = await withRequestDeadline(Promise.resolve('ok'), 100, (fn) => setTimeout(fn, 100), (timer) => { cleared = true; clearTimeout(timer); });
  assert.equal(result, 'ok');
  assert.equal(cleared, true);
});

test('deadline rejects a hung request promptly with a typed error', async () => {
  await assert.rejects(withRequestDeadline(new Promise(() => {}), 5), error => {
    assert.ok(error instanceof RequestDeadlineError);
    assert.equal(error.code, 'REQUEST_DEADLINE_EXCEEDED');
    return true;
  });
});

test('deadline preserves upstream rejection without retrying', async () => {
  const failure = new Error('upstream unavailable');
  await assert.rejects(withRequestDeadline(Promise.reject(failure), 100), error => error === failure);
});

test('invalid deadlines reject immediately', async () => {
  await assert.rejects(withRequestDeadline(Promise.resolve('ok'), 0), RangeError);
});
