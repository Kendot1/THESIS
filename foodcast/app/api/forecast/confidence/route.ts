import { resolveConfidenceEvidence, type ConfidenceContext } from '../../../lib/forecast-evidence';
import { approvedConfidenceRegistry } from '../../../lib/confidence-registry.server';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
 const q=new URL(request.url).searchParams;
 const fields=['category','name','variant','origin','unit','modelId','route','contractId','horizon','forecastOrigin','modelOrigin','targetStart','targetEnd','targetStatistic'] as const;
 if(fields.some(k=>!q.get(k)) || !['daily','weekly','monthly'].includes(q.get('horizon')??'')
  || !['forecastOrigin','modelOrigin'].every(k=>/^\d{4}-\d{2}-\d{2}$/.test(q.get(k)??''))
  || !q.has('lead') || !q.has('leadStart') || !q.has('leadEnd')) return Response.json({error:'Exact identity, model, contract, origin and lead scope required'},{status:400});
 const commodityId = q.get('commodityId');
 const context={...Object.fromEntries(fields.map(k=>[k,q.get(k)])),...(commodityId?{commodityId}:{}),lead:q.get('lead')==='null'?null:Number(q.get('lead')),leadStart:Number(q.get('leadStart')),leadEnd:Number(q.get('leadEnd'))} as ConfidenceContext;
 if(!Number.isInteger(context.leadStart)||!Number.isInteger(context.leadEnd)||context.leadStart<1||context.leadEnd<context.leadStart
  ||(context.lead!==null&&(!Number.isInteger(context.lead)||context.lead<1))) return Response.json({error:'Invalid lead scope'},{status:400});
 const evidence=resolveConfidenceEvidence(context,await approvedConfidenceRegistry());
 const evaluation = evidence.kind === 'approvedconfidence' ? (evidence.evaluation ?? null) : null;
 return Response.json({
  context,
  evidence,
  confidence_pct:evidence.value,
  metric:evaluation ? 'PICP' : null,
  evaluation,
  calibration_version:evaluation ? 'split_conformal_picp_v1' : null,
 },{headers:{'Cache-Control':'no-store'}});
}
