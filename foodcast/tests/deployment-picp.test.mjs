import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { loadTs } from './load-ts.mjs';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1')), '../artifacts/picp');
const registry = loadTs('../app/lib/confidence-registry.server.ts');

test('bundled PICP metadata and forecast provenance hashes match', async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
  const bytes = fs.readFileSync(path.join(root, 'runs', manifest.active_run, 'metadata.json'));
  const loaded = await registry.loadActiveModelPicpArtifact(root);
  assert.ok(loaded);
  assert.equal(loaded.artifact.metadata_sha256, createHash('sha256').update(bytes).digest('hex'));
  assert.equal(loaded.artifact.records.length, 291);
});

test('historical PICP endpoint reads packaged evidence for all three horizons', async () => {
  const route = loadTs('../app/api/forecast/confidence/route.ts', {
    '../../../lib/confidence-registry.server': {
      ...registry,
      loadActiveModelPicpArtifact: () => registry.loadActiveModelPicpArtifact(root),
    },
  });
  for (const horizon of ['daily', 'weekly', 'monthly']) {
    const query = new URLSearchParams({ scope: 'historical-picp', category: 'Fruits', name: 'Avocado', variant: 'Standard', origin: 'Local', unit: 'kg', horizon });
    const response = await route.GET(new Request(`https://example.test/api/forecast/confidence?${query}`));
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.scope, 'historical-picp');
    assert.equal(body.evidence.kind, 'historicalpicp');
    assert.ok(body.evidence.value > 0 && body.evidence.value <= 100);
  }
});
