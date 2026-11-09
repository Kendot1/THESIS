import test from 'node:test';
import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadTs } from './load-ts.mjs';

const lib = loadTs('../app/lib/forecast-evidence.ts');
const registryMod = loadTs('../app/lib/confidence-registry.server.ts');
const { GET } = loadTs('../app/api/forecast/confidence/route.ts', {
  '../../../lib/confidence-registry.server': registryMod,
});
const ConfidenceWidget = loadTs('../app/components/ConfidenceWidget.tsx').default;

const ACTIVE_MODEL_RUN_ID = '20261001T025925Z_0661960a';

function makeContext(overrides = {}) {
  const horizon = overrides.horizon ?? 'daily';
  const targetStatistic =
    horizon === 'daily'
      ? 'daily_price'
      : horizon === 'weekly'
        ? 'rolling_7day_mean'
        : 'rolling_30day_mean';
  return {
    commodityId: '703eb577-2291-4f9f-8c6a-f6cce9727280',
    category: 'Fruits',
    name: 'Avocado',
    variant: 'Standard',
    origin: 'Local',
    unit: 'kg',
    modelId: ACTIVE_MODEL_RUN_ID,
    route: 'model',
    contractId: 'rolling_daily7_weekly4_monthly30_v2',
    horizon,
    lead: 1,
    forecastOrigin: '2026-11-09',
    modelOrigin: '2026-11-06',
    leadStart: 4,
    leadEnd: horizon === 'daily' ? 10 : horizon === 'weekly' ? 31 : 33,
    targetStart: '2026-11-10',
    targetEnd: horizon === 'daily' ? '2026-11-10' : horizon === 'weekly' ? '2026-11-16' : '2026-12-09',
    targetStatistic,
    ...overrides,
  };
}

test('calculatePicpFromIntervals computes exact PICP and rejects invalid or incomplete intervals', () => {
  const valid = lib.calculatePicpFromIntervals([
    { actual: 100, lowerBound: 90, upperBound: 110 },
    { actual: 105, lowerBound: 95, upperBound: 110 },
    { actual: 120, lowerBound: 100, upperBound: 115 },
    { actual: 95, lowerBound: 90, upperBound: 100 },
  ]);
  assert.equal(valid.status, 'valid');
  assert.equal(valid.coveredCount, 3);
  assert.equal(valid.sampleCount, 4);
  assert.equal(valid.empiricalCoverage, 75);

  const empty = lib.calculatePicpFromIntervals([]);
  assert.equal(empty.status, 'insufficient_data');
  assert.equal(empty.empiricalCoverage, null);

  const inverted = lib.calculatePicpFromIntervals([
    { actual: 100, lowerBound: 115, upperBound: 95 },
  ]);
  assert.equal(inverted.status, 'invalid_intervals');
  assert.equal(inverted.empiricalCoverage, null);

  const incomplete = lib.calculatePicpFromIntervals([
    { actual: 100, lowerBound: NaN, upperBound: 110 },
  ]);
  assert.equal(incomplete.status, 'invalid_intervals');
  assert.equal(incomplete.empiricalCoverage, null);
});

test('active model run 20261001T025925Z_0661960a serves verified PICP across different commodities and forecast horizons', async () => {
  const registry = await registryMod.approvedConfidenceRegistry();
  assert.ok(registry.length > 0, 'Active model PICP registry must be non-empty');

  // 1. Avocado across daily, weekly, monthly
  for (const [horizon, expectedPicp, expectedCovered, expectedTotal] of [
    ['daily', 83.7838, 62, 74],
    ['weekly', 87.6289, 255, 291],
    ['monthly', 89.7436, 280, 312],
  ]) {
    const ctx = makeContext({ horizon });
    const q = new URLSearchParams(Object.entries(ctx).map(([k, v]) => [k, String(v)]));
    const res = await GET(new Request(`http://localhost/api/forecast/confidence?${q}`));
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.metric, 'PICP');
    assert.equal(body.evidence.kind, 'approvedconfidence');
    assert.equal(body.confidence_pct, expectedPicp);
    assert.equal(body.evaluation.model_run_id, ACTIVE_MODEL_RUN_ID);
    assert.equal(body.evaluation.commodity_id, '703eb577-2291-4f9f-8c6a-f6cce9727280');
    assert.equal(body.evaluation.forecast_horizon, horizon);
    assert.equal(body.evaluation.target_coverage, 95);
    assert.equal(body.evaluation.covered_count, expectedCovered);
    assert.equal(body.evaluation.sample_count, expectedTotal);
    assert.equal(body.evaluation.evaluation_period, '2025-09-13..2026-09-07');
  }

  // 2. Different commodity: Baguio Beans across daily, weekly, monthly
  for (const [horizon, expectedPicp] of [
    ['daily', 91.8919],
    ['weekly', 87.9725],
    ['monthly', 87.5],
  ]) {
    const ctx = makeContext({
      commodityId: 'f575a935-e6e2-49a3-8d09-ec60beb4687b',
      category: 'Vegetables',
      name: 'Baguio Beans',
      variant: 'Standard',
      origin: 'Local',
      unit: 'kg',
      horizon,
    });
    const evidence = lib.resolveConfidenceEvidence(ctx, registry);
    assert.equal(evidence.kind, 'approvedconfidence');
    assert.equal(evidence.value, expectedPicp);
    assert.equal(evidence.evaluation.commodity_id, 'f575a935-e6e2-49a3-8d09-ec60beb4687b');
    assert.equal(evidence.evaluation.forecast_horizon, horizon);
  }

  // 3. Different commodity: Banana Lakatan
  const lakatanDaily = lib.resolveConfidenceEvidence(
    makeContext({
      commodityId: 'cb9d4a57-985f-46a9-a2c6-5e07b72abf12',
      category: 'Fruits',
      name: 'Banana',
      variant: 'Lakatan',
      origin: 'Local',
      unit: 'kg',
      horizon: 'daily',
    }),
    registry
  );
  assert.equal(lakatanDaily.kind, 'approvedconfidence');
  assert.equal(lakatanDaily.value, 100);
});

test('missing evaluation data, invalid/incomplete intervals, and non-active model runs fail closed and never fabricate confidence', async () => {
  const registry = await registryMod.approvedConfidenceRegistry();

  // 1. Commodity with insufficient calibration data in active model run (Kadiwa Rice Premium RFA5 daily)
  const missingDataCtx = makeContext({
    commodityId: 'b66c15be-898d-45c4-9250-a52c9cdac0c9',
    category: 'Rice',
    name: 'Rice',
    variant: 'Kadiwa Premium (RFA5)',
    origin: 'Local',
    unit: 'kg',
    horizon: 'daily',
  });
  const missingResult = lib.resolveConfidenceEvidence(missingDataCtx, registry);
  assert.equal(missingResult.kind, 'unavailable');
  assert.equal(missingResult.value, null);

  // 2. Non-active model run (e.g. previous champion 20260930T143815Z_006170b1)
  const nonActiveCtx = makeContext({ modelId: '20260930T143815Z_006170b1' });
  const nonActiveResult = lib.resolveConfidenceEvidence(nonActiveCtx, registry);
  assert.equal(nonActiveResult.kind, 'unavailable');
  assert.equal(nonActiveResult.value, null);

  // 3. Invalid or incomplete interval record (e.g. negative half-width, mismatched PICP ratio, or invalid_intervals status)
  const validAvocado = registry.find(
    (r) => r.method === 'out_of_sample_picp' && r.name === 'Avocado' && r.forecast_horizon === 'daily'
  );
  assert.ok(validAvocado);
  for (const corrupted of [
    { ...validAvocado, status: 'invalid_intervals' },
    { ...validAvocado, interval_half_width_php: -5 },
    { ...validAvocado, interval_half_width_php: NaN },
    { ...validAvocado, empirical_coverage: 99.9 }, // does not match covered_count / sample_count
    { ...validAvocado, sample_count: 5, covered_count: 5, empirical_coverage: 100 }, // below min test samples
    { ...validAvocado, calibration_sample_count: 10 }, // below min conformal calibration samples
    { ...validAvocado, active_model_run_id: 'other_active_run' }, // not the active model run
  ]) {
    const res = lib.resolveConfidenceEvidence(makeContext({ horizon: 'daily' }), [corrupted]);
    assert.equal(res.kind, 'unavailable');
    assert.equal(res.value, null);
  }
});

test('ConfidenceWidget renders loading state, PICP percentage with supporting info, and Confidence unavailable state', async () => {
  const registry = await registryMod.approvedConfidenceRegistry();
  const avocadoDaily = lib.resolveConfidenceEvidence(makeContext({ horizon: 'daily' }), registry);

  // 1. Loading state while fetching
  const loadingHtml = renderToStaticMarkup(
    ConfidenceWidget({ evidence: undefined, loading: true, modelRunId: ACTIVE_MODEL_RUN_ID })
  );
  assert.match(loadingHtml, /Loading confidence\.\.\./);
  assert.match(loadingHtml, /data-confidence-state="loading"/);
  assert.match(loadingHtml, new RegExp(ACTIVE_MODEL_RUN_ID));
  assert.doesNotMatch(loadingHtml, /\d+%/);

  // 2. Valid PICP evaluation state (exact 83.8% without whole-number rounding, green color, no extra subtitle lines)
  const validHtml = renderToStaticMarkup(ConfidenceWidget({ evidence: avocadoDaily }));
  assert.match(validHtml, /data-confidence-state="available"/);
  assert.match(validHtml, /83\.8%/);
  assert.match(validHtml, /#2E7D32/);
  assert.doesNotMatch(validHtml, /PICP 83\.8%/);
  assert.doesNotMatch(validHtml, /Run 20261001T025925Z_0661960a/);
  assert.doesNotMatch(validHtml, /Eval 2025-09-13\.\.2026-09-07/);

  // 2b. Color tiers: green (>=80), orange (60..79.9), red (<60)
  const orangeHtml = renderToStaticMarkup(
    ConfidenceWidget({ evidence: { ...avocadoDaily, value: 72.4 } })
  );
  assert.match(orangeHtml, /72\.4%/);
  assert.match(orangeHtml, /#ff8134/);

  const redHtml = renderToStaticMarkup(
    ConfidenceWidget({ evidence: { ...avocadoDaily, value: 45.6 } })
  );
  assert.match(redHtml, /45\.6%/);
  assert.match(redHtml, /#C62828/);

  // 3. Unavailable state when evaluation data is missing or invalid
  const unavailEvidence = lib.resolveConfidenceEvidence(
    makeContext({ modelId: '20260930T143815Z_006170b1' }),
    registry
  );
  const unavailHtml = renderToStaticMarkup(
    ConfidenceWidget({ evidence: unavailEvidence, modelRunId: '20260930T143815Z_006170b1' })
  );
  assert.match(unavailHtml, /data-confidence-state="unavailable"/);
  assert.match(unavailHtml, /Confidence unavailable/);
  assert.doesNotMatch(unavailHtml, /\d+%/);
});

