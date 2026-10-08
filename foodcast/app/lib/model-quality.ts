import type { ForecastConfidenceMetric, ForecastQualityMetrics, ForecastStatus } from './data';

type ProductMetric = NonNullable<ForecastQualityMetrics['product_metrics']>[string];
type SnapshotMetrics = Omit<ForecastQualityMetrics, 'product_metrics'> & {
  product_metrics?: Record<string, Omit<ProductMetric, 'confidence_by_horizon'> & {
    // JSON imports widen literal values. Validate them at this boundary.
    confidence_by_horizon?: unknown;
  }>;
};

interface CapabilitySnapshot {
  modelRunId: string;
  metrics: SnapshotMetrics;
}

function isConfidenceMetric(value: unknown, lead: 1 | 7 | 30): value is ForecastConfidenceMetric {
  if (!value || typeof value !== 'object') return false;
  const metric = value as Record<string, unknown>;
  const nonnegative = (number: unknown) => number === null
    || (typeof number === 'number' && Number.isFinite(number) && number >= 0);
  return metric.forecast_horizon_days === lead
    && nonnegative(metric.confidence_score)
    && (metric.confidence_score === null || (metric.confidence_score as number) <= 100)
    && typeof metric.confidence_level === 'string'
    && ['Very High', 'High', 'Moderate', 'Low', 'Very Low', 'Insufficient data'].includes(metric.confidence_level)
    && [metric.mae, metric.rmse, metric.mape].every(nonnegative)
    && typeof metric.sample_count === 'number' && Number.isInteger(metric.sample_count) && metric.sample_count >= 0
    && metric.evaluation_source === 'chronological_validation'
    && typeof metric.confidence_method === 'string' && metric.confidence_method.length > 0
    && typeof metric.model_version === 'string' && metric.model_version.length > 0
    && typeof metric.evidence_status === 'string'
    && ['validated', 'insufficient_data', 'unverified_provenance'].includes(metric.evidence_status);
}

function readSnapshotMetrics(metrics: SnapshotMetrics): ForecastQualityMetrics {
  // Without product metrics, the snapshot already has the full runtime shape.
  if (!metrics.product_metrics) return metrics as ForecastQualityMetrics;
  const product_metrics: NonNullable<ForecastQualityMetrics['product_metrics']> = {};
  for (const [id, product] of Object.entries(metrics.product_metrics)) {
    const { confidence_by_horizon: raw, ...rest } = product;
    const confidence_by_horizon: ProductMetric['confidence_by_horizon'] = {};
    if (raw && typeof raw === 'object') {
      for (const [horizon, lead] of [['daily', 1], ['weekly', 7], ['monthly', 30]] as const) {
        const metric = (raw as Record<string, unknown>)[horizon];
        if (isConfidenceMetric(metric, lead)) confidence_by_horizon[horizon] = metric;
      }
    }
    product_metrics[id] = { ...rest, confidence_by_horizon };
  }
  return { ...metrics, product_metrics };
}

/** Bootstrap only the exact evaluated model; never reuse another model's score. */
export function withModelCapability(status: ForecastStatus | null, snapshot: CapabilitySnapshot): ForecastStatus | null {
  if (!status) return null;
  const measured = (metrics: Pick<ForecastQualityMetrics, 'evaluation_source' | 'success_definition'> | null | undefined) =>
    metrics?.evaluation_source === 'historical_holdout'
      && metrics.success_definition === 'absolute_percentage_error_at_most_tolerance';
  const modelMetrics = measured(status.modelMetrics) ? status.modelMetrics
    : measured(status.metrics) ? status.metrics
    : status.modelRunId === snapshot.modelRunId && measured(snapshot.metrics) ? readSnapshotMetrics(snapshot.metrics) : null;
  return { ...status, modelMetrics };
}
