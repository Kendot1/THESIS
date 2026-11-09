"use client";
import { useEffect, useState } from 'react';
import ConfidenceWidget from './ConfidenceWidget';
import { resolveConfidenceEvidence, type ConfidenceContext, type ForecastEvidence } from '../lib/forecast-evidence';
/** Selection-keyed response: old product/horizon results are never displayed during a request. */
export default function ForecastConfidenceBadge({context, historicalPicp=false}:{context:ConfidenceContext; historicalPicp?:boolean}) {
 const key=JSON.stringify({context,historicalPicp});
 const complete=historicalPicp
  ? [context.category,context.name,context.variant,context.origin,context.unit,context.horizon].every(Boolean)
  : [context.category,context.name,context.variant,context.origin,context.unit,context.modelId,context.route,context.contractId,context.horizon,context.forecastOrigin,context.modelOrigin,context.targetStart,context.targetEnd,context.targetStatistic].every(Boolean);
 const [result,setResult]=useState<{key:string;evidence:ForecastEvidence}|null>(null);
 useEffect(()=>{
  let cancelled=false;
  const selection=JSON.parse(key) as {context:ConfidenceContext;historicalPicp:boolean};
  const {context:selectionContext}=selection;
  const required=selection.historicalPicp
   ? [selectionContext.category,selectionContext.name,selectionContext.variant,selectionContext.origin,selectionContext.unit,selectionContext.horizon]
   : [selectionContext.category,selectionContext.name,selectionContext.variant,selectionContext.origin,selectionContext.unit,selectionContext.modelId,selectionContext.route,selectionContext.contractId,selectionContext.horizon,selectionContext.forecastOrigin,selectionContext.modelOrigin,selectionContext.targetStart,selectionContext.targetEnd,selectionContext.targetStatistic];
  if(required.some(value=>!value)) return;
  const query=new URLSearchParams(Object.entries(selectionContext).filter(([,v])=>v!==undefined).map(([k,v])=>[k,String(v)]));
  if(selection.historicalPicp) query.set('scope','historical-picp');
  fetch(`/api/forecast/confidence?${query}`,{cache:'no-store'}).then(async response=>{
   if(!response.ok){
    if(!cancelled)setResult({key,evidence:selection.historicalPicp?{kind:'unavailable',value:null,label:'Confidence level',details:'Historical PICP unavailable.'}:resolveConfidenceEvidence(selectionContext)});
    return;
   }
   const body=await response.json();
   const contextMatches=selection.historicalPicp
    ? body.context?.category===selectionContext.category && body.context?.name===selectionContext.name
      && body.context?.variant===selectionContext.variant && body.context?.origin===selectionContext.origin
      && body.context?.unit===selectionContext.unit && body.context?.horizon===selectionContext.horizon
      && (!selectionContext.commodityId || body.context?.commodityId===selectionContext.commodityId)
    : Object.entries(selectionContext).every(([k,v])=>v===undefined || body.context?.[k]===v);
   if(!cancelled && (!selection.historicalPicp || body.scope==='historical-picp') && contextMatches) setResult({key,evidence:body.evidence});
  }).catch(()=>{
   if(!cancelled)setResult({key,evidence:selection.historicalPicp?{kind:'unavailable',value:null,label:'Confidence level',details:'Historical PICP unavailable.'}:resolveConfidenceEvidence(selectionContext)});
  });
  return ()=>{cancelled = true;};
 },[key]);
 const loading = complete && result?.key !== key;
 const evidence=result?.key === key ? result.evidence : resolveConfidenceEvidence(context);
 return <div data-confidence-horizon={context.horizon} data-confidence-product={`${context.category}||${context.name}||${context.variant}||${context.origin}||${context.unit}`}><ConfidenceWidget evidence={evidence} loading={loading} modelRunId={context.modelId || undefined} historicalPicp={historicalPicp}/></div>;
}
