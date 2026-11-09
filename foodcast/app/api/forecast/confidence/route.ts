import { resolveConfidenceEvidence, type ConfidenceContext } from '../../../lib/forecast-evidence';
import { approvedConfidenceRegistry, loadActiveModelPicpArtifact } from '../../../lib/confidence-registry.server';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
 const q=new URL(request.url).searchParams;
 const historicalPicp = q.get('scope') === 'historical-picp';
 const fields=['category','name','variant','origin','unit','modelId','route','contractId','horizon','forecastOrigin','modelOrigin','targetStart','targetEnd','targetStatistic'] as const;
 const requiredFields = historicalPicp ? ['category','name','variant','origin','unit','horizon'] as const : fields;
 if(requiredFields.some(k=>!q.get(k)) || !['daily','weekly','monthly'].includes(q.get('horizon')??'')
  || (!historicalPicp && (!['forecastOrigin','modelOrigin'].every(k=>/^\d{4}-\d{2}-\d{2}$/.test(q.get(k)??''))
  || !q.has('lead') || !q.has('leadStart') || !q.has('leadEnd')))) return Response.json({error:'Exact identity, model, contract, origin and lead scope required'},{status:400});
 const commodityId = q.get('commodityId');
 const context={...Object.fromEntries(fields.map(k=>[k,q.get(k)])),...(commodityId?{commodityId}:{}),lead:q.get('lead')==='null'?null:Number(q.get('lead')),leadStart:Number(q.get('leadStart')),leadEnd:Number(q.get('leadEnd'))} as ConfidenceContext;
 if(!historicalPicp && (!Number.isInteger(context.leadStart)||!Number.isInteger(context.leadEnd)||context.leadStart<1||context.leadEnd<context.leadStart
  ||(context.lead!==null&&(!Number.isInteger(context.lead)||context.lead<1)))) return Response.json({error:'Invalid lead scope'},{status:400});
  if (historicalPicp) {
    const loaded = await loadActiveModelPicpArtifact();
    const record = loaded?.artifact.records.find(row => row.model_run_id === loaded.activeRunId
      && row.status === 'valid' && row.forecast_horizon === q.get('horizon')
      && (!q.get('commodityId') || row.commodity_id === q.get('commodityId'))
      && (row.series_key === [q.get('category'),q.get('name'),q.get('variant'),q.get('origin'),q.get('unit')].join('||'))
      && typeof row.empirical_coverage === 'number' && Number.isFinite(row.empirical_coverage)
      && row.empirical_coverage >= 0 && row.empirical_coverage <= 100
      && Number.isInteger(row.covered_count) && Number.isInteger(row.sample_count)
      && row.sample_count >= 10 && row.covered_count >= 0 && row.covered_count <= row.sample_count
      && Math.abs(row.empirical_coverage - (row.covered_count / row.sample_count) * 100) < 0.001);
    const value = record?.empirical_coverage ?? null;
    return Response.json({scope:'historical-picp', context, evidence:value == null ? {kind:'unavailable',value:null,label:'Historical PICP',details:'Historical PICP unavailable.'} : {kind: 'historicalpicp',value,label:'Historical PICP',details:'Historical prediction interval coverage.',evidenceId:`picp:${loaded?.activeRunId}:${record?.commodity_id}:${record?.forecast_horizon}:${record?.target_coverage}`}}, {headers:{'Cache-Control':'no-store'}});
  }
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
