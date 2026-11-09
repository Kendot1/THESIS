import type { ProductAccuracy } from "../lib/product-accuracy";

const percent = (value: number | null) => value == null ? "Unavailable" : `${value.toFixed(2)}%`;
const pesos = (value: number | null) => value == null ? "Unavailable" : `₱${value.toFixed(2)}`;

import type { ForecastEvidence } from '../lib/forecast-evidence';
import ConfidenceWidget, { ConfidenceRing } from './ConfidenceWidget';
function EvidenceBadges({evidence}:{evidence?:ForecastEvidence}) {return <div className="space-y-3"><ConfidenceWidget evidence={evidence?.kind==='approvedconfidence'?evidence:undefined}/>{evidence?.kind==='historicalaccuracy' && <div data-testid="historical-accuracy" title={evidence.details} className="flex items-center gap-3 text-xs font-bold"><ConfidenceRing value={evidence.value} color="#059669" label="Historical forecast accuracy"/><span>HISTORICAL FORECAST ACCURACY</span></div>}</div>;}

/** Original-contract retrospective preview; never a deployed-model accuracy claim. */
export default function ProductAccuracyPanel({ accuracy, evidence }: { accuracy: ProductAccuracy | null; evidence?: ForecastEvidence }) {
  if (!accuracy) return <section aria-label="Forecast Accuracy"><h2>Forecast Accuracy</h2>
    <p>No matching historical evaluation available.</p><EvidenceBadges evidence={evidence} /></section>;
  return <section aria-label="Forecast Accuracy" className="rounded-2xl border p-5 space-y-3">
    <h2>Forecast Accuracy</h2>
    <EvidenceBadges evidence={evidence} />
    <p>{accuracy.product_name} · {accuracy.product_variant} · {accuracy.product_category} · {accuracy.origin} · {accuracy.unit}</p>
    <dl>
      <dt>Historical Relative Accuracy</dt><dd>{percent(accuracy.historical_relative_accuracy_pct)}</dd>
      <dt>MAE</dt><dd>{pesos(accuracy.mae_php)}</dd>
      <dt>RMSE</dt><dd>{pesos(accuracy.rmse_php)}</dd>
      <dt>MAPE</dt><dd>{percent(accuracy.mape_pct)}</dd>
      <dt>Historical ±₱5 hit rate</dt><dd>{percent(accuracy.historical_php5_hit_rate_pct)}</dd>
      <dt>Forecast coverage</dt><dd>{percent(accuracy.forecast_coverage_pct)}</dd>
    </dl>
    <p>{accuracy.horizon}{accuracy.lead == null ? " · all applicable leads" : ` · lead ${accuracy.lead}`} · n={accuracy.evaluated_predictions} / {accuracy.required_keys} required keys</p>
    <p>{accuracy.evaluation_period_start} – {accuracy.evaluation_period_end}</p>
    <p>Model: {accuracy.model_id}. Contract: {accuracy.contract_id}.</p>
    <p>Historical Relative Accuracy is 100 − MAPE: historical average percentage closeness, not a probability or guarantee of future accuracy.</p>
    <p>Excluded from MAPE for zero or near-zero actual prices: {accuracy.excluded_zero_near_zero_actuals}.</p>
    {accuracy.relative_accuracy_warning && <p role="note">{accuracy.relative_accuracy_warning}</p>}
    <p>Historical research reference; not evidence that this model is deployed.</p>
  </section>;
}
