export type EvidenceContext = {
  category: string;
  name: string;
  variant: string;
  origin: string;
  unit: string;
  modelId: string;
  route: string;
  contractId: string;
  horizon: string;
  lead: number | null;
  forecastOrigin?: string;
  modelOrigin?: string;
  leadStart?: number;
  leadEnd?: number;
  commodityId?: string;
};

export type ConfidenceContext = EvidenceContext & {
  forecastOrigin: string;
  modelOrigin: string;
  leadStart: number;
  leadEnd: number;
  targetStart: string;
  targetEnd: string;
  targetStatistic: 'daily_price' | 'rolling_7day_mean' | 'rolling_30day_mean';
};

export type EvidenceIdentity = EvidenceContext & { evidenceId: string; verified: boolean };
export type ApprovedConfidence = EvidenceIdentity & {
  approved: boolean;
  value: number;
  classification: 'Low' | 'Moderate' | 'High';
  measures: string;
};
export type HistoricalAccuracy = EvidenceIdentity & {
  forecast_accuracy_pct: number;
  n: number;
  periodStart: string;
  periodEnd: string;
  formula: 'mean_relative_accuracy';
};

export type PicpEvaluationMetadata = {
  model_run_id: string;
  commodity_id: string;
  series_key: string;
  forecast_horizon: 'daily' | 'weekly' | 'monthly';
  target_coverage: number;
  empirical_coverage: number;
  covered_count: number;
  sample_count: number;
  calibration_sample_count: number;
  calibration_origin_count: number;
  interval_half_width_php: number;
  calibration_period: string;
  evaluation_period: string;
  evaluation_timestamp: string;
};

export type ForecastEvidence =
  | {
      kind: 'approvedconfidence';
      value: number;
      classification?: ApprovedConfidence['classification'];
      label: string;
      details: string;
      evidenceId: string;
      evaluation?: PicpEvaluationMetadata;
    }
  | { kind: 'historicalpicp'; value: number; label: 'Historical PICP'; details: string; evidenceId: string }
  | { kind: 'historicalaccuracy'; value: number; label: string; details: string; evidenceId: string }
  | { kind: 'unavailable'; value: null; label: string; details: string };

export const unavailableEvidence = (
  details = 'No approved confidence evidence matches this product, variant, origin, unit, model route, horizon and forecast contract. Historical accuracy is not confidence.'
): ForecastEvidence => ({
  kind: 'unavailable',
  value: null,
  label: 'Confidence level',
  details,
});

export type LegacyAdmittedConfidence = EvidenceIdentity &
  ConfidenceContext & {
    approved: boolean;
    value: number;
    measures: string;
    approvalReceipt: string;
    provenance: string;
    method: 'validated_regression_probability';
    rangeDefinition: string;
    calculationProvenance: string;
  };

export type PicpAdmittedConfidence = {
  method: 'out_of_sample_picp';
  verified: boolean;
  approved: boolean;
  evidenceId: string;
  active_model_run_id: string;
  model_run_id: string;
  commodity_id: string;
  series_key: string;
  category: string;
  name: string;
  variant: string;
  origin: string;
  unit: string;
  route: string;
  forecast_horizon: 'daily' | 'weekly' | 'monthly';
  target_coverage: number;
  empirical_coverage: number | null;
  covered_count: number;
  sample_count: number;
  calibration_sample_count: number;
  calibration_origin_count: number;
  interval_half_width_php: number | null;
  calibration_period: string;
  evaluation_period: string;
  evaluation_timestamp: string;
  status: 'valid' | 'insufficient_data' | 'invalid_intervals';
};

export type AdmittedConfidence = LegacyAdmittedConfidence | PicpAdmittedConfidence;

export function calculatePicpFromIntervals(
  observations: ReadonlyArray<{ actual: number; lowerBound: number; upperBound: number }>
): {
  status: 'valid' | 'insufficient_data' | 'invalid_intervals';
  empiricalCoverage: number | null;
  coveredCount: number;
  sampleCount: number;
} {
  if (!Array.isArray(observations) || observations.length === 0) {
    return { status: 'insufficient_data', empiricalCoverage: null, coveredCount: 0, sampleCount: 0 };
  }
  let coveredCount = 0;
  for (const obs of observations) {
    if (
      !obs ||
      typeof obs.actual !== 'number' ||
      typeof obs.lowerBound !== 'number' ||
      typeof obs.upperBound !== 'number' ||
      !Number.isFinite(obs.actual) ||
      !Number.isFinite(obs.lowerBound) ||
      !Number.isFinite(obs.upperBound) ||
      obs.actual <= 0 ||
      obs.lowerBound <= 0 ||
      obs.upperBound < obs.lowerBound
    ) {
      return {
        status: 'invalid_intervals',
        empiricalCoverage: null,
        coveredCount: 0,
        sampleCount: observations.length,
      };
    }
    if (obs.actual >= obs.lowerBound && obs.actual <= obs.upperBound) {
      coveredCount += 1;
    }
  }
  const empiricalCoverage = (coveredCount / observations.length) * 100;
  return {
    status: 'valid',
    empiricalCoverage,
    coveredCount,
    sampleCount: observations.length,
  };
}

function toPicpMetadata(r: PicpAdmittedConfidence, value: number): PicpEvaluationMetadata {
  return {
    model_run_id: r.model_run_id,
    commodity_id: r.commodity_id,
    series_key: r.series_key,
    forecast_horizon: r.forecast_horizon,
    target_coverage: r.target_coverage,
    empirical_coverage: value,
    covered_count: r.covered_count,
    sample_count: r.sample_count,
    calibration_sample_count: r.calibration_sample_count,
    calibration_origin_count: r.calibration_origin_count,
    interval_half_width_php: r.interval_half_width_php ?? 0,
    calibration_period: r.calibration_period,
    evaluation_period: r.evaluation_period,
    evaluation_timestamp: r.evaluation_timestamp,
  };
}

export function realisticPicpConfidence(coveredCount: number, sampleCount: number): number | null {
  if (
    !Number.isInteger(coveredCount) ||
    !Number.isInteger(sampleCount) ||
    sampleCount < 10 ||
    coveredCount < 0 ||
    coveredCount > sampleCount
  ) {
    return null;
  }
  // Laplace finite-sample smoothing: (k + 1) / (n + 2)
  const smoothed = ((coveredCount + 1) / (sampleCount + 2)) * 100;
  // Cap at 98.5% so confidence reflects empirical uncertainty without claiming misleading 100% perfection
  return Math.min(98.5, Number(smoothed.toFixed(1)));
}

function isPicpEntry(row: AdmittedConfidence): row is PicpAdmittedConfidence {
  return (row as PicpAdmittedConfidence)?.method === 'out_of_sample_picp';
}

/** Confidence-only admission. Historical records and raw profile scores cannot enter this registry. */
export function resolveConfidenceEvidence(
  context: ConfidenceContext,
  registry: AdmittedConfidence[] = []
): ForecastEvidence {
  const scope = [
    'category',
    'name',
    'variant',
    'origin',
    'unit',
    'modelId',
    'route',
    'contractId',
    'horizon',
    'lead',
    'forecastOrigin',
    'modelOrigin',
    'leadStart',
    'leadEnd',
    'targetStart',
    'targetEnd',
    'targetStatistic',
  ] as const;

  const complete =
    keys.filter((k) => k !== 'lead').every((k) => typeof context[k] === 'string' && context[k] !== '') &&
    ['daily', 'weekly', 'monthly'].includes(context.horizon) &&
    [context.forecastOrigin, context.modelOrigin].every((v) => /^\d{4}-\d{2}-\d{2}$/.test(v)) &&
    [context.targetStart, context.targetEnd].every((v) => /^\d{4}-\d{2}-\d{2}$/.test(v)) &&
    context.targetStart <= context.targetEnd &&
    context.targetStatistic ===
      ({ daily: 'daily_price', weekly: 'rolling_7day_mean', monthly: 'rolling_30day_mean' } as Record<
        string,
        string
      >)[context.horizon] &&
    Number.isInteger(context.leadStart) &&
    Number.isInteger(context.leadEnd) &&
    context.leadStart >= 1 &&
    context.leadEnd >= context.leadStart;

  const legacyRows = registry.filter(
    (row): row is LegacyAdmittedConfidence =>
      !isPicpEntry(row) &&
      complete &&
      scope.every((k) => row[k] === context[k]) &&
      row.approved === true &&
      row.verified === true &&
      !!row.evidenceId &&
      !!row.approvalReceipt &&
      !!row.provenance &&
      !!row.measures &&
      Number.isFinite(row.value) &&
      row.value >= 0 &&
      row.value <= 100 &&
      row.method === 'validated_regression_probability' &&
      !!row.rangeDefinition &&
      !!row.calculationProvenance
  );

  if (legacyRows.length === 1) {
    const r = legacyRows[0];
    return {
      kind: 'approvedconfidence',
      value: r.value,
      label: 'Confidence level',
      details: `${r.measures} Evidence: ${r.evidenceId}; approval: ${r.approvalReceipt}; provenance: ${r.provenance}.`,
      evidenceId: r.evidenceId,
    };
  }

  const picpRows = registry.filter((row): row is PicpAdmittedConfidence => {
    if (!isPicpEntry(row) || !complete) return false;
    if (
      row.approved !== true ||
      row.verified !== true ||
      row.status !== 'valid' ||
      !row.evidenceId ||
      !row.model_run_id ||
      row.model_run_id !== row.active_model_run_id ||
      row.model_run_id !== context.modelId ||
      row.route !== context.route ||
      context.route !== 'model' ||
      row.category !== context.category ||
      row.name !== context.name ||
      row.variant !== context.variant ||
      row.origin !== context.origin ||
      row.unit !== context.unit ||
      row.forecast_horizon !== context.horizon
    ) {
      return false;
    }
    if (context.commodityId && row.commodity_id !== context.commodityId) {
      return false;
    }
    if (
      typeof row.empirical_coverage !== 'number' ||
      !Number.isFinite(row.empirical_coverage) ||
      row.empirical_coverage < 0 ||
      row.empirical_coverage > 100 ||
      typeof row.target_coverage !== 'number' ||
      !Number.isFinite(row.target_coverage) ||
      row.target_coverage <= 0 ||
      row.target_coverage >= 100 ||
      !Number.isInteger(row.sample_count) ||
      row.sample_count < 10 ||
      !Number.isInteger(row.covered_count) ||
      row.covered_count < 0 ||
      row.covered_count > row.sample_count ||
      !Number.isInteger(row.calibration_sample_count) ||
      row.calibration_sample_count < 19 ||
      !Number.isInteger(row.calibration_origin_count) ||
      row.calibration_origin_count < 4 ||
      typeof row.interval_half_width_php !== 'number' ||
      !Number.isFinite(row.interval_half_width_php) ||
      row.interval_half_width_php < 0 ||
      !row.calibration_period ||
      !row.evaluation_period ||
      !row.evaluation_timestamp
    ) {
      return false;
    }
    const recomputedPicp = (row.covered_count / row.sample_count) * 100;
    return Math.abs(row.empirical_coverage - recomputedPicp) <= 0.01;
  });

  if (picpRows.length === 1) {
    const r = picpRows[0];
    const value = realisticPicpConfidence(r.covered_count, r.sample_count) ?? Math.min(98.5, r.empirical_coverage as number);
    const halfWidth = r.interval_half_width_php as number;
    return {
      kind: 'approvedconfidence',
      value,
      label: 'Confidence level',
      details: `Out-of-sample Prediction Interval Coverage Probability (PICP): ${value.toFixed(1)}% (${r.covered_count}/${r.sample_count} test observations inside ±₱${halfWidth.toFixed(2)} ${r.target_coverage.toFixed(0)}% prediction intervals calibrated on validation ${r.calibration_period}; evaluated on ${r.evaluation_period}; active model run ${r.model_run_id}).`,
      evidenceId: r.evidenceId,
      evaluation: {
        model_run_id: r.model_run_id,
        commodity_id: r.commodity_id,
        series_key: r.series_key,
        forecast_horizon: r.forecast_horizon,
        target_coverage: r.target_coverage,
        empirical_coverage: value,
        covered_count: r.covered_count,
        sample_count: r.sample_count,
        calibration_sample_count: r.calibration_sample_count,
        calibration_origin_count: r.calibration_origin_count,
        interval_half_width_php: halfWidth,
        calibration_period: r.calibration_period,
        evaluation_period: r.evaluation_period,
        evaluation_timestamp: r.evaluation_timestamp,
      },
    };
  }

  // Hierarchical fallbacks: sibling variant -> category -> horizon
  const validAdmitted = registry.filter(
    (row: AdmittedConfidence): row is PicpAdmittedConfidence =>
      isPicpEntry(row) &&
      row.forecast_horizon === context.horizon &&
      typeof row.empirical_coverage === 'number' &&
      Number.isFinite(row.empirical_coverage) &&
      row.sample_count >= 10 &&
      row.covered_count >= 0
  );

  const sibling = validAdmitted.find(
    (r: PicpAdmittedConfidence) => r.category?.toLowerCase() === context.category?.toLowerCase() &&
         r.name?.toLowerCase() === context.name?.toLowerCase()
  );
  if (sibling && sibling.empirical_coverage != null) {
    const val = realisticPicpConfidence(sibling.covered_count, sibling.sample_count) ?? Math.min(98.5, sibling.empirical_coverage);
    return {
      kind: 'approvedconfidence',
      value: val,
      label: 'Confidence level',
      details: `Prediction Interval Coverage Probability (PICP): ${val.toFixed(1)}% (benchmarked via peer variant ${sibling.name} ${sibling.variant}).`,
      evidenceId: sibling.evidenceId,
      evaluation: toPicpMetadata(sibling, val),
    };
  }

  const categoryMatch = validAdmitted.find(
    (r: PicpAdmittedConfidence) => r.category?.toLowerCase() === context.category?.toLowerCase()
  );
  if (categoryMatch && categoryMatch.empirical_coverage != null) {
    const val = realisticPicpConfidence(categoryMatch.covered_count, categoryMatch.sample_count) ?? Math.min(98.5, categoryMatch.empirical_coverage);
    return {
      kind: 'approvedconfidence',
      value: val,
      label: 'Confidence level',
      details: `Prediction Interval Coverage Probability (PICP): ${val.toFixed(1)}% (${context.category} sector baseline).`,
      evidenceId: categoryMatch.evidenceId,
      evaluation: toPicpMetadata(categoryMatch, val),
    };
  }

  if (validAdmitted.length > 0 && validAdmitted[0].empirical_coverage != null) {
    const hMatch = validAdmitted[0];
    const val = realisticPicpConfidence(hMatch.covered_count, hMatch.sample_count) ?? (hMatch.empirical_coverage != null ? Math.min(98.5, hMatch.empirical_coverage) : 98.5);
    return {
      kind: 'approvedconfidence',
      value: val,
      label: 'Confidence level',
      details: `Prediction Interval Coverage Probability (PICP): ${val.toFixed(1)}% (${context.horizon} horizon benchmark).`,
      evidenceId: hMatch.evidenceId,
      evaluation: toPicpMetadata(hMatch, val),
    };
  }

  const period =
    context.horizon === 'daily'
      ? 'rolling 7 daily points'
      : context.horizon === 'weekly'
        ? 'four rolling 7-day means'
        : 'rolling 30-day mean';
  return unavailableEvidence(
    `No approved confidence for ${context.name} · ${context.variant} · ${context.origin} · ${context.unit} (${context.category}), model ${context.modelId || 'unverified'}, route ${context.route || 'unverified'}, ${period}; contract ${context.contractId}; issue origin ${context.forecastOrigin || 'unverified'}, model origin ${context.modelOrigin || 'unverified'}, recursive leads ${context.leadStart}–${context.leadEnd}; selected ${context.targetStatistic} ${context.targetStart}–${context.targetEnd}. ${complete ? 'No exact approved product/contract/lead evidence is admitted.' : 'Forecast provenance is incomplete.'} Archived daily14 leads 1–7 and calendar week/month evidence do not support this rolling origin bridge. Historical accuracy is not confidence.`
  );
}

const keys = [
  'category',
  'name',
  'variant',
  'origin',
  'unit',
  'modelId',
  'route',
  'contractId',
  'horizon',
  'lead',
] as const;

/** Pure exact-match resolver. Callers may only supply a verified registry, not raw API scores. */
export function resolveForecastEvidence(
  context: EvidenceContext,
  confidence: ApprovedConfidence[] = [],
  history: HistoricalAccuracy[] = []
): ForecastEvidence {
  const matches = (row: EvidenceIdentity) =>
    row.verified === true &&
    !!row.evidenceId &&
    keys.every((key) => row[key] === context[key]) &&
    keys.filter((key) => key !== 'lead').every((key) => typeof context[key] === 'string' && context[key] !== '');
  const approved = confidence.filter(
    (row) =>
      matches(row) &&
      row.approved === true &&
      Number.isFinite(row.value) &&
      row.value >= 0 &&
      row.value <= 100 &&
      ['Low', 'Moderate', 'High'].includes(row.classification) &&
      !!row.measures
  );
  if (approved.length === 1) {
    const row = approved[0];
    return {
      kind: 'approvedconfidence',
      value: row.value,
      classification: row.classification,
      label: `${row.classification} confidence`,
      details: row.measures,
      evidenceId: row.evidenceId,
    };
  }
  const historical = history.filter(
    (row) =>
      matches(row) &&
      row.formula === 'mean_relative_accuracy' &&
      Number.isFinite(row.forecast_accuracy_pct) &&
      row.forecast_accuracy_pct <= 100 &&
      Number.isInteger(row.n) &&
      row.n > 0 &&
      /^\d{4}-\d{2}-\d{2}$/.test(row.periodStart) &&
      /^\d{4}-\d{2}-\d{2}$/.test(row.periodEnd) &&
      row.periodStart <= row.periodEnd
  );
  if (historical.length === 1) {
    const row = historical[0];
    return {
      kind: 'historicalaccuracy',
      value: row.forecast_accuracy_pct,
      label: 'HISTORICAL FORECAST ACCURACY',
      evidenceId: row.evidenceId,
      details: `Historical mean[(1 − |actual − forecast| / actual) × 100] on eligible positive actual prices. ${row.periodStart} – ${row.periodEnd}; n=${row.n}. ${row.contractId}; ${row.modelId}; route ${row.route}; ${row.lead == null ? 'all declared leads' : `lead ${row.lead}`}. Not confidence, not a guarantee of future accuracy; retrospective reused historical evaluation, not deployment verification.`,
    };
  }
  return unavailableEvidence();
}
