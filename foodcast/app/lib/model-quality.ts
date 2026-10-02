import type { ForecastQualityMetrics, ForecastStatus } from './data';

interface CapabilitySnapshot {
  modelRunId: string;
  metrics: ForecastQualityMetrics;
}

/** Bootstrap only the exact evaluated model; never reuse another model's score. */
export function withModelCapability(status: ForecastStatus | null, snapshot: CapabilitySnapshot): ForecastStatus | null {
  if (!status) return null;
  const measured = (metrics: ForecastQualityMetrics | null | undefined) =>
    metrics?.evaluation_source === 'historical_holdout'
      && metrics.success_definition === 'absolute_percentage_error_at_most_tolerance';
  const modelMetrics = measured(status.modelMetrics) ? status.modelMetrics
    : measured(status.metrics) ? status.metrics
    : status.modelRunId === snapshot.modelRunId && measured(snapshot.metrics) ? snapshot.metrics : null;
  return { ...status, modelMetrics };
}
