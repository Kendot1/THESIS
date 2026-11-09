import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('tag paths do not request news during build', () => {
  const source = fs.readFileSync(new URL('../app/tags/[id]/page.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /generateStaticParams/);
  assert.match(source, /dynamic\s*=\s*['"]force-dynamic['"]/);
});

test('live-data routes do not fetch during prerender', () => {
  for (const route of ['Predict', 'MarketData', 'Map', 'About']) {
    const source = fs.readFileSync(new URL(`../app/${route}/page.tsx`, import.meta.url), 'utf8');
    assert.match(source, /dynamic\s*=\s*['"]force-dynamic['"]/);
  }
});

test('product dynamic paths do not request the remote product catalog during build', async () => {
  const source = fs.readFileSync(new URL('../app/Product/[id]/page.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /generateStaticParams/);
  assert.match(source, /dynamic\s*=\s*['"]force-dynamic['"]/);
});
