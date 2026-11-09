import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { loadTs } from './load-ts.mjs';

const repo = new URL('../../', import.meta.url);
test('PICP metadata survives the Git index without changing its signed bytes', () => {
 const root='foodcast/artifacts/picp/';
 const run='20261001T025925Z_0661960a';
 const indexed=execFileSync('git',['show',':'+root+'runs/'+run+'/metadata.json'],{cwd:repo});
 const artifact=JSON.parse(fs.readFileSync(new URL('../artifacts/picp/confidence_evaluations/'+run+'.json',import.meta.url)));
 assert.equal(createHash('sha256').update(indexed).digest('hex'),artifact.metadata_sha256);
});

test('performance reads the packaged original predictions without a sibling audits directory', async () => {
 const manifest=JSON.parse(fs.readFileSync(new URL('../app/lib/historical-accuracy.json',import.meta.url)));
 const {homepagePerformance}=loadTs('../app/lib/historical-performance.server.ts',{'./historical-accuracy.json':manifest});
 const before=process.cwd();
 try {
  process.chdir((await import('node:url')).fileURLToPath(new URL('../',import.meta.url)));
  const result=await homepagePerformance();
  assert.ok(result.historical_forecast_accuracy_pct>96 && result.historical_forecast_accuracy_pct<97);
 } finally {process.chdir(before);}
});
