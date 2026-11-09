import { resolveConfidenceEvidence, type ConfidenceContext, type PicpAdmittedConfidence } from '../../../lib/forecast-evidence';
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
    const seriesKey = [q.get('category'),q.get('name'),q.get('variant'),q.get('origin'),q.get('unit')].join('||');
    const loaded = await loadActiveModelPicpArtifact();
    let record = loaded?.artifact.records.find(row => row.model_run_id === loaded.activeRunId
      && row.status === 'valid' && row.forecast_horizon === q.get('horizon')
      && (row.series_key === seriesKey || (!q.get('commodityId') || row.commodity_id === q.get('commodityId')))
      && typeof row.empirical_coverage === 'number' && Number.isFinite(row.empirical_coverage)
      && row.empirical_coverage >= 0 && row.empirical_coverage <= 100
      && Number.isInteger(row.covered_count) && Number.isInteger(row.sample_count)
      && row.sample_count >= 10 && row.covered_count >= 0 && row.covered_count <= row.sample_count
      && Math.abs(row.empirical_coverage - (row.covered_count / row.sample_count) * 100) < 0.001);
    if (!record) {
      const reg = await approvedConfidenceRegistry();
      const found = reg.find((r): r is PicpAdmittedConfidence => r.method === 'out_of_sample_picp'
        && r.forecast_horizon === q.get('horizon')
        && (r.series_key === seriesKey || (!q.get('commodityId') || r.commodity_id === q.get('commodityId'))));
      if (found) {
        record = {
          model_run_id: found.model_run_id,
          commodity_id: found.commodity_id,
          series_key: found.series_key,
          forecast_horizon: found.forecast_horizon,
          target_coverage: found.target_coverage,
          empirical_coverage: found.empirical_coverage,
          covered_count: found.covered_count,
          sample_count: found.sample_count,
          calibration_sample_count: found.calibration_sample_count,
          calibration_origin_count: found.calibration_origin_count,
          interval_half_width_php: found.interval_half_width_php,
          calibration_period: found.calibration_period,
          evaluation_period: found.evaluation_period,
          evaluation_timestamp: found.evaluation_timestamp,
          status: found.status,
        };
      }
    }
    const value = record?.empirical_coverage ?? null;
    return Response.json({scope:'historical-picp', context, evidence:value == null ? {kind:'unavailable',value:null,label:'Historical PICP',details:'Historical PICP unavailable.'} : {kind: 'historicalpicp',value,label:'Historical PICP',details:'Historical prediction interval coverage.',evidenceId:`picp:${record?.model_run_id || loaded?.activeRunId}:${record?.commodity_id}:${record?.forecast_horizon}:${record?.target_coverage}`}}, {headers:{'Cache-Control':'no-store'}});
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
