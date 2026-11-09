export interface ProductAccuracy {
  product_category: string;
  product_name: string;
  product_variant: string;
  origin: string;
  unit: string;
  series: string;
  horizon: "daily" | "weekly" | "monthly";
  lead: number | null;
  contract_id: string;
  model_id: string;
  evaluation_period_start: string;
  evaluation_period_end: string;
  evaluated_predictions: number;
  required_keys: number;
  forecast_coverage_pct: number | null;
  historical_relative_accuracy_pct: number | null;
  mae_php: number | null;
  rmse_php: number | null;
  mape_pct: number | null;
  historical_php5_hit_rate_pct: number | null;
  excluded_zero_near_zero_actuals: number;
  relative_accuracy_warning: string | null;
  confidence: null;
  confidence_status: "Not calibrated";
}

/** Exact identity and contract matching only; never substitute an overall average. */
export function selectProductAccuracy(rows: ProductAccuracy[], identity: Pick<ProductAccuracy,
  "product_category" | "product_name" | "product_variant" | "origin" | "unit">,
  contractId: string, horizon: ProductAccuracy["horizon"], lead: number | null = null): ProductAccuracy | null {
  const matches = rows.filter(row => row.contract_id === contractId && row.horizon === horizon
    && row.lead === lead && row.product_category === identity.product_category
    && row.product_name === identity.product_name && row.product_variant === identity.product_variant
    && row.origin === identity.origin && row.unit === identity.unit);
  return matches.length === 1 ? matches[0] : null;
}
