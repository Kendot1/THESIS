import type { ForecastConfidenceMetric, ForecastQualityMetrics, ForecastStatus,
  ForecastStepConfidenceMetric, HistoricalForecastAccuracy } from './data';

type ProductMetric = NonNullable<ForecastQualityMetrics['product_metrics']>[string];
type SnapshotMetrics = Omit<ForecastQualityMetrics, 'product_metrics'> & {
  product_metrics?: Record<string, Omit<ProductMetric, 'confidence_by_horizon' | 'confidence_by_step'> & {
    // JSON imports widen literal values. Validate them at this boundary.
    confidence_by_horizon?: unknown;
    confidence_by_step?: unknown;
  }>;
};

interface CapabilitySnapshot {
  modelRunId: string;
  metrics: SnapshotMetrics;
  historical_accuracy?: HistoricalForecastAccuracy;
}

function isConfidenceMetric(value: unknown, lead: 1 | 7 | 30): value is ForecastConfidenceMetric {
  if (!value || typeof value !== 'object') return false;
  const metric = value as Record<string, unknown>;
  const nonnegative = (number: unknown) => number === null
    || (typeof number === 'number' && Number.isFinite(number) && number >= 0);
  const evaluationIsTrusted = metric.evaluation_source === 'chronological_validation';
  const validScore = metric.evidence_status === 'validated'
    && typeof metric.sample_count === 'number' && metric.sample_count >= 8
    && typeof metric.sample_origin_count === 'number' && metric.sample_origin_count >= 8
    && metric.confidence_score != null && Number.isFinite(metric.confidence_score)
    && (metric.confidence_score as number) >= 0 && (metric.confidence_score as number) <= 100
    && ['Very High', 'High', 'Moderate', 'Low', 'Very Low'].includes(String(metric.confidence_level))
    && [metric.mae, metric.rmse, metric.mape].every(value => typeof value === 'number'
      && Number.isFinite(value) && value >= 0);
  const insufficient = metric.evidence_status === 'insufficient_data'
    && typeof metric.sample_count === 'number' && metric.sample_count >= 0
    && (typeof metric.sample_origin_count === 'number'
      ? metric.sample_origin_count < 8 : metric.sample_count < 8)
    && metric.confidence_score === null && metric.confidence_level === 'Insufficient data';
  return metric.forecast_horizon_days === lead
    && nonnegative(metric.confidence_score)
    && (metric.confidence_score === null || (metric.confidence_score as number) <= 100)
    && typeof metric.confidence_level === 'string'
    && ['Very High', 'High', 'Moderate', 'Low', 'Very Low', 'Insufficient data'].includes(metric.confidence_level)
    && [metric.mae, metric.rmse, metric.mape].every(nonnegative)
    && typeof metric.sample_count === 'number' && Number.isInteger(metric.sample_count) && metric.sample_count >= 0
    && evaluationIsTrusted
    && typeof metric.confidence_method === 'string' && metric.confidence_method.length > 0
    && typeof metric.model_version === 'string' && metric.model_version.length > 0
    && evaluationIsTrusted && (validScore || insufficient);
}

function isConfidenceStepMetric(value: unknown, step: number): value is ForecastStepConfidenceMetric {
  if (!value || typeof value !== 'object') return false;
  const metric = value as Record<string, unknown>;
  const finiteNonnegative = (number: unknown) => number === null
    || (typeof number === 'number' && Number.isFinite(number) && number >= 0);
  const validScore = metric.evidence_status === 'validated'
    && metric.sample_count != null && Number.isInteger(metric.sample_count) && (metric.sample_count as number) >= 8
    && typeof metric.sample_origin_count === 'number' && Number.isInteger(metric.sample_origin_count)
    && metric.sample_origin_count >= 8
    && typeof metric.confidence_score === 'number' && Number.isFinite(metric.confidence_score)
    && metric.confidence_score >= 0 && metric.confidence_score <= 100
    && ['Very High', 'High', 'Moderate', 'Low', 'Very Low'].includes(String(metric.confidence_level))
    && [metric.mae, metric.rmse, metric.mape].every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0);
  const insufficient = metric.evidence_status === 'insufficient_data'
    && typeof metric.sample_count === 'number' && Number.isInteger(metric.sample_count)
    && metric.sample_count >= 0
    && (typeof metric.sample_origin_count === 'number'
      ? metric.sample_origin_count < 8 : metric.sample_count < 8)
    && metric.confidence_score === null && metric.confidence_level === 'Insufficient data';
  return metric.forecast_step === step && Number.isInteger(metric.forecast_horizon_days)
    && (metric.forecast_horizon_days as number) >= 1 && (metric.forecast_horizon_days as number) <= 30
    && (metric.evaluation_source === 'chronological_validation')
    && finiteNonnegative(metric.confidence_score)
    && [metric.mae, metric.rmse, metric.mape].every(finiteNonnegative)
    && typeof metric.confidence_method === 'string' && metric.confidence_method.length > 0
    && typeof metric.model_version === 'string' && metric.model_version.length > 0
    && (validScore || insufficient);
}

function readSnapshotMetrics(metrics: SnapshotMetrics): ForecastQualityMetrics {
  // Without product metrics, the snapshot already has the full runtime shape.
  if (!metrics.product_metrics) return metrics as ForecastQualityMetrics;
  const product_metrics: NonNullable<ForecastQualityMetrics['product_metrics']> = {};
  for (const [id, product] of Object.entries(metrics.product_metrics)) {
    const { confidence_by_horizon: raw, confidence_by_step: rawSteps, ...rest } = product;
    const confidence_by_horizon: ProductMetric['confidence_by_horizon'] = {};
    if (raw && typeof raw === 'object') {
      for (const [horizon, lead] of [['daily', 1], ['weekly', 7], ['monthly', 30]] as const) {
        const metric = (raw as Record<string, unknown>)[horizon];
        if (isConfidenceMetric(metric, lead)) confidence_by_horizon[horizon] = metric;
      }
    }
    const confidence_by_step: ProductMetric['confidence_by_step'] = {};
    if (rawSteps && typeof rawSteps === 'object') {
      for (const horizon of ['daily', 'weekly', 'monthly'] as const) {
        const rawHorizon = (rawSteps as Record<string, unknown>)[horizon];
        if (!rawHorizon || typeof rawHorizon !== 'object') continue;
        const steps: Record<number, ForecastStepConfidenceMetric> = {};
        for (const [key, value] of Object.entries(rawHorizon as Record<string, unknown>)) {
          const step = Number(key);
          if (Number.isInteger(step) && step >= 1 && isConfidenceStepMetric(value, step)) {
            steps[step] = value;
          }
        }
        confidence_by_step[horizon] = steps;
      }
    }
    product_metrics[id] = { ...rest, confidence_by_horizon, confidence_by_step };
  }
  return { ...metrics, product_metrics };
}

/** Bootstrap only the exact evaluated model; never reuse another model's score. */
export function withModelCapability(status: ForecastStatus | null, snapshot: CapabilitySnapshot): ForecastStatus | null {
  if (!status) return null;
  const measured = (metrics: Pick<ForecastQualityMetrics, 'evaluation_source' | 'success_definition'> | null | undefined) =>
    metrics?.evaluation_source === 'chronological_validation'
      && metrics.success_definition === 'absolute_percentage_error_at_most_tolerance';
  const baseMetrics = measured(status.modelMetrics) ? status.modelMetrics
    : measured(status.metrics) ? status.metrics
    : status.modelRunId === snapshot.modelRunId && measured(snapshot.metrics) ? readSnapshotMetrics(snapshot.metrics) : null;
  let modelMetrics = baseMetrics;
  if (status.modelRunId === snapshot.modelRunId && measured(snapshot.metrics)) {
    const snapshotMetrics = readSnapshotMetrics(snapshot.metrics);
    const product_metrics = { ...(baseMetrics?.product_metrics ?? {}) };
    for (const [identity, snapshotProduct] of Object.entries(snapshotMetrics.product_metrics ?? {})) {
      if (!snapshotProduct.confidence_by_horizon) continue;
      product_metrics[identity] = {
        ...snapshotProduct,
        ...product_metrics[identity],
        confidence_by_horizon: snapshotProduct.confidence_by_horizon,
        confidence_by_step: snapshotProduct.confidence_by_step,
      };
    }
    modelMetrics = {
      ...(baseMetrics ?? snapshotMetrics),
      // The live status can report a null aggregate score for this same run.
      // Use the evaluated snapshot score only when the model run IDs match.
      prediction_success: baseMetrics?.prediction_success ?? snapshotMetrics.prediction_success,
      within_10_tolerance: snapshotMetrics.within_10_tolerance,
      within_10_definition: snapshotMetrics.within_10_definition,
      within_10_accuracy_pct: snapshotMetrics.within_10_accuracy_pct,
      within_10_count: snapshotMetrics.within_10_count,
      within_10_sample_count: snapshotMetrics.within_10_sample_count,
      metric_aggregation: snapshotMetrics.metric_aggregation,
      training_through: snapshotMetrics.training_through,
      product_metrics,
    };
  }
  return {
    ...status,
    modelMetrics,
    historicalAccuracy: status.modelRunId === snapshot.modelRunId
      ? snapshot.historical_accuracy ?? null
      : null,
  };
}
