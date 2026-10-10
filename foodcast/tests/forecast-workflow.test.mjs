import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('daily workflow publishes from the restored model without training or scoring outcomes', () => {
  const workflow = readFileSync(new URL('../../.github/workflows/main.yml', import.meta.url), 'utf8');
  const commands = workflow.split('\n').filter(line => /^\s+run:/.test(line)).join('\n');
  assert.match(commands, /python -m utils\.r2_sync download/);
  assert.match(commands, /python main\.py predict --horizon monthly/);
  assert.doesNotMatch(commands, /python main\.py (train|evaluate)\b/);
  assert.doesNotMatch(commands, /frozen_holdout\.py score/);
  assert.doesNotMatch(commands, /python -m utils\.r2_sync upload/);
  assert.ok(commands.indexOf('utils.r2_sync download') < commands.indexOf('main.py predict'));
});

test('news crawler temporary directory is set in step context where runner is available', () => {
  const workflow = readFileSync(new URL('../../.github/workflows/main.yml', import.meta.url), 'utf8');
  const newsJob = workflow.split('  scrape_news:')[1].split('  train_model:')[0];
  assert.doesNotMatch(newsJob.split('    steps:')[0], /runner\./);
  const steps = newsJob.split(/\n      - name: /);
  for (const name of ['Install dependencies', 'Run News Scraper']) {
    const step = steps.find(value => value.startsWith(name));
    assert.ok(step, name);
    assert.match(step, /CRAWL4_AI_BASE_DIRECTORY: \$\{\{ runner\.temp \}\}/);
  }
});
