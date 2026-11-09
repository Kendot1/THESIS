'use client';
import { useMemo, useState } from 'react';
import ProductView from '../client/Product';
import type { Product } from '../lib/data';
import { encryptId } from '../../lib/idCipher';
type Row = {series:string;forecast_origin:string;history_date:string;anchor:number;target_date:string;step:number;prediction:number;actual:number|null};
export default function JuneLayout({rows,products}:{rows:Row[];products:Product[]}) {
 const identity=(p:Product)=>[p.category,p.name,p.variant,p.origin,p.unit].join('||');
 const matches=products.filter(p=>rows.some(r=>r.series===identity(p)));
 const [choice,setChoice]=useState(matches.find(p=>identity(p)===rows[0]?.series)?.id ?? matches[0]?.id ?? '');
 const base=matches.find(p=>p.id===choice);
 const context=useMemo(()=>{
  if(!base)return null;
  const available=rows.filter(r=>r.series===identity(base));
  // Latest origins are right-censored: select a saved path with seven dated reports.
  const origins=[...new Set(available.map(r=>r.forecast_origin))].sort();
  const origin=origins.filter(o=>available.filter(r=>r.forecast_origin===o && r.target_date).length>=7).at(-1);
  if(!origin)return null;
  const selected=available.filter(r=>r.forecast_origin===origin && r.target_date).sort((a,b)=>a.step-b.step);
  const historical=available.filter(r=>r.actual!=null && r.target_date && r.target_date<origin).sort((a,b)=>a.target_date.localeCompare(b.target_date));
  const anchor=selected[0]?.anchor;
  if(anchor==null || !selected.length)return null;
  const preview:Product={...base,forecastModelRunId:'june-original-lstm-preview',forecastOriginDate:origin,currentPrice:anchor,previousPrice:anchor,predictedPrice:selected[0].prediction,confidence_pct:null,
   forecastData:selected.map(r=>({date:r.target_date,name:`Report step ${r.step}`,actual:r.actual,predicted:r.prediction,horizon:'daily',forecast_step:r.step})),
   dailyForecast:selected.map(r=>({date:r.target_date,predicted_price:r.prediction,reasoning:'Saved June LSTM next-report prediction, not live calendar forecasting.'}))};
  return {preview,params:Promise.resolve({id:encryptId(base.id)})};
 },[base,rows]);
 return <><aside className="p-4 bg-amber-100 text-black"><strong>June LSTM · Historical frontend preview</strong><p>Saved next-report predictions in the existing product layout—not today’s forecasts. “Daily” uses report dates here; weekly/monthly forecasts are unavailable. DEVELOPMENT_REUSED; no calibrated confidence.</p><label>Product <select value={choice} onChange={e=>setChoice(e.target.value)}>{matches.map(p=><option key={p.id} value={p.id}>{p.name} · {p.variant} · {p.unit}</option>)}</select></label></aside>{context?<ProductView key={choice} params={context.params} initialProducts={[context.preview]} historicalPreview={context.preview}/>:<p>No safely matched historical product context available.</p>}</>;
}
