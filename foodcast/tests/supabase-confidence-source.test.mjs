import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
test('serving confidence registry reads Supabase without local artifact fallback',()=>{
 const s=fs.readFileSync(new URL('../app/lib/confidence-registry.server.ts',import.meta.url),'utf8');
 const serving=s.slice(s.indexOf('export async function approvedConfidenceRegistry('));
 assert.match(serving,/read_model_confidence_evaluations/);
 assert.doesNotMatch(serving,/loadActiveModelPicpArtifact\(/);
 assert.match(serving,/independently_approved/);
});
