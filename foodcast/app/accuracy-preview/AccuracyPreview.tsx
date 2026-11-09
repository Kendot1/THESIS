"use client";

import { useState } from "react";
import ProductAccuracyPanel from "../components/ProductAccuracyPanel";

import { selectProductAccuracy, type ProductAccuracy } from "../lib/product-accuracy";

import {resolveForecastEvidence, type HistoricalAccuracy} from '../lib/forecast-evidence';

export default function AccuracyPreview({ products, leads, history }: { products: ProductAccuracy[]; leads: ProductAccuracy[]; history: HistoricalAccuracy[] }) {
  const identities = [...new Map(products.map(row => [row.series, row])).values()];
  const [series, setSeries] = useState(identities.find(row => row.product_name === "Lettuce" && row.product_variant === "Romaine")?.series ?? identities[0]?.series ?? "");
  const [horizon, setHorizon] = useState<ProductAccuracy["horizon"]>("daily");
  const [lead, setLead] = useState<number | null>(null);
  const [contractMode,setContractMode]=useState('original');
  const identity = identities.find(row => row.series === series);
  const reference = products.find(row => row.series === series && row.horizon === horizon);
  const availableLeads = leads.filter(row => row.series === series && row.horizon === horizon);
  const accuracy = identity && reference ? selectProductAccuracy(lead == null ? products : leads,
    identity, reference.contract_id, horizon, lead) : null;
  return <main className="max-w-4xl mx-auto p-6 space-y-6">
    <h1 className="text-2xl font-bold">FOODCAST — Local Historical Accuracy Preview</h1>
    <p>Saved historical evaluations only. This does not change forecasts, select models or establish deployed model identity.</p>

    <div className="grid gap-4 sm:grid-cols-3">
      <label>Product<select aria-label="Product" className="block w-full border p-2" value={series} onChange={event => { setSeries(event.target.value); setLead(null); }}>
        {identities.map(row => <option key={row.series} value={row.series}>{row.product_name} · {row.product_variant} · {row.origin} · {row.unit} · {row.product_category}</option>)}
      </select></label>
      <label>Horizon<select aria-label="Horizon" className="block w-full border p-2" value={horizon} onChange={event => { setHorizon(event.target.value as ProductAccuracy["horizon"]); setLead(null); }}>
        <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
      </select></label>
      <label>Lead<select aria-label="Lead" className="block w-full border p-2" value={lead ?? "all"} onChange={event => setLead(event.target.value === "all" ? null : Number(event.target.value))}>
        <option value="all">All applicable leads</option>{availableLeads.map(row => <option key={row.lead} value={row.lead!}>{row.lead}</option>)}
      </select></label>
    </div>
    <label className="block">Evidence contract<select aria-label="Evidence contract" className="block w-full border p-2" value={contractMode} onChange={event=>setContractMode(event.target.value)}><option value="original">Original archived historical contract (not live)</option><option value="rolling">Current rolling forecast — unsupported evidence</option></select></label>
    <ProductAccuracyPanel accuracy={accuracy} evidence={resolveForecastEvidence({category:identity?.product_category??'',name:identity?.product_name??'',variant:identity?.product_variant??'',origin:identity?.origin??'',unit:identity?.unit??'',modelId:reference?.model_id??'',route:'incumbent_served',contractId:contractMode==='original' ? reference?.contract_id??'' : 'current_rolling_forecast',horizon,lead},[],history)} />
  </main>;
}
