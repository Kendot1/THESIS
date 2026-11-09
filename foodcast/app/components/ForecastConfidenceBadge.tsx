"use client";
import { useEffect, useState } from 'react';
import ConfidenceWidget from './ConfidenceWidget';
import { resolveConfidenceEvidence, type ConfidenceContext, type ForecastEvidence } from '../lib/forecast-evidence';
/** Selection-keyed response: old product/horizon results are never displayed during a request. */
export default function ForecastConfidenceBadge({context}:{context:ConfidenceContext}) {
 const key=JSON.stringify(context);
 const complete=[context.category,context.name,context.variant,context.origin,context.unit,context.modelId,context.route,context.contractId,context.horizon,context.forecastOrigin,context.modelOrigin,context.targetStart,context.targetEnd,context.targetStatistic].every(Boolean);
 const [result,setResult]=useState<{key:string;evidence:ForecastEvidence}|null>(null);
 useEffect(()=>{
  let cancelled=false;
  const selection=JSON.parse(key) as ConfidenceContext;
  const required=[selection.category,selection.name,selection.variant,selection.origin,selection.unit,selection.modelId,selection.route,selection.contractId,selection.horizon,selection.forecastOrigin,selection.modelOrigin,selection.targetStart,selection.targetEnd,selection.targetStatistic];
  if(required.some(value=>!value)) return;
  const query=new URLSearchParams(Object.entries(selection).filter(([,v])=>v!==undefined).map(([k,v])=>[k,String(v)]));
  fetch(`/api/forecast/confidence?${query}`,{cache:'no-store'}).then(async response=>{
   if(!response.ok){
    if(!cancelled)setResult({key,evidence:resolveConfidenceEvidence(selection)});
    return;
   }
   const body=await response.json();
   if(!cancelled && Object.entries(selection).every(([k,v])=>v===undefined || body.context?.[k]===v))setResult({key,evidence:body.evidence});
  }).catch(()=>{
   if(!cancelled)setResult({key,evidence:resolveConfidenceEvidence(selection)});
  });
  return ()=>{cancelled = true;};
 },[key]);
 const loading = complete && result?.key !== key;
 const evidence=result?.key === key ? result.evidence : resolveConfidenceEvidence(context);
 return <div data-confidence-horizon={context.horizon} data-confidence-product={`${context.category}||${context.name}||${context.variant}||${context.origin}||${context.unit}`}><ConfidenceWidget evidence={evidence} loading={loading} modelRunId={context.modelId || undefined}/></div>;
}
