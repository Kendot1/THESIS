import assert from 'node:assert/strict';
import test from 'node:test';
import { loadForecastStatus } from './status.ts';

function database(responses) {
  const queries = [];
  return {
    queries,
    from(table) {
      assert.equal(table, 'forecast_runs', 'Status must never query live outcomes');
      const query = { table, orders: [] };
      queries.push(query);
      return {
        select(columns) { query.columns = columns; return this; },
        order(column, options) { query.orders.push([column, options]); return this; },
        limit(count) { assert.equal(count, 1); return this; },
        async maybeSingle() { assert.ok(responses.length); return responses.shift(); },
      };
    },
  };
}

test('status returns the exact persisted metrics using only the latest run', async () => {
  const metrics = { evaluation_source: 'chronological_validation', mae: 9, product_metrics: {} };
  const db = database([{ data: { model_run_id: 'model', generated_at: '2026-10-09',
    horizon: 30, row_count: 3961, metrics }, error: null }]);
  assert.deepEqual(await loadForecastStatus(db), {
    modelRunId: 'model', generatedAt: '2026-10-09', horizon: 30, rowCount: 3961,
    metrics, modelMetrics: metrics,
  });
  assert.equal(db.queries.length, 1);
  assert.deepEqual(db.queries[0].orders, [
    ['generated_at', { ascending: false }], ['id', { ascending: false }],
  ]);
});

test('empty history and malformed saved metrics remain unavailable', async () => {
  assert.equal(await loadForecastStatus(database([{ data: null }])), null);
  for (const metrics of [null, undefined, [], 'invalid']) {
    const result = await loadForecastStatus(database([{ data: { metrics } }]));
    assert.equal(result.metrics, null);
    assert.equal(result.modelMetrics, null);
  }
});

test('missing metrics column supports timestamps without calculating replacement scores', async () => {
  const db = database([
    { error: { code: '42703', message: 'column forecast_runs.metrics does not exist' } },
    { data: { model_run_id: 'legacy' } },
  ]);
  const result = await loadForecastStatus(db);
  assert.equal(result.modelRunId, 'legacy');
  assert.equal(result.metrics, null);
  assert.equal(db.queries.length, 2);
  assert.ok(!db.queries[1].columns.includes('metrics'));
});

test('unrelated query errors are propagated', async () => {
  const error = { code: '57014', message: 'metrics query timed out' };
  const db = database([{ error }]);
  await assert.rejects(loadForecastStatus(db), value => value === error);
  assert.equal(db.queries.length, 1);
});
