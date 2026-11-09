'use client';
import type { Product } from '../lib/data';
import ConfidenceWidget, { ConfidenceRing } from './ConfidenceWidget';

import type { EvidenceContext, HistoricalAccuracy } from '../lib/forecast-evidence';
import { resolveForecastEvidence } from '../lib/forecast-evidence';

export default function HistoricalIndicator({ product, horizon, context, history = [] }: { product: Product; horizon: string; context?: EvidenceContext; history?: HistoricalAccuracy[] }) {
  // No admitted calibrator. Historical ±₱5 hit frequency is not used as confidence.
  const exact = context ?? { category:product.category, name:product.name, variant:product.variant, origin:product.origin, unit:product.unit,
    modelId:product.forecastModelRunId ?? '', route:product.forecastSource ?? '', contractId:'unverified_current_contract', horizon, lead:null };
  const historical=resolveForecastEvidence({...exact,horizon}, [], history);
  return <div className="space-y-3"><ConfidenceWidget />{historical.kind==='historicalaccuracy' && <div data-testid="historical-accuracy" title={historical.details} className="flex items-center gap-3 text-xs font-bold"><ConfidenceRing value={historical.value} color="#059669" label="Historical forecast accuracy"/><span>HISTORICAL FORECAST ACCURACY</span></div>}</div>;
}
