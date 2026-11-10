import { resolveConfidenceEvidence, realisticPicpConfidence, type ConfidenceContext, type PicpAdmittedConfidence } from '../../../lib/forecast-evidence';
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
    const category = q.get('category') ?? '';
    const name = q.get('name') ?? '';
    const variant = q.get('variant') ?? '';
    const origin = q.get('origin') ?? '';
    const unit = q.get('unit') ?? '';
    const horizon = q.get('horizon') as 'daily' | 'weekly' | 'monthly';
    const commodityId = q.get('commodityId');
    const seriesKey = [category, name, variant, origin, unit].join('||');
    const loaded = await loadActiveModelPicpArtifact();
    const records = loaded?.artifact.records ?? [];

    const validRecords = records.filter(row =>
      row.model_run_id === loaded?.activeRunId &&
      row.forecast_horizon === horizon &&
      row.status === 'valid' &&
      typeof row.empirical_coverage === 'number' &&
      Number.isFinite(row.empirical_coverage) &&
      row.sample_count >= 10 &&
      row.covered_count >= 0 &&
      row.covered_count <= row.sample_count
    );

    let tier: 'exact' | 'sibling' | 'category' | 'horizon' = 'exact';
    let record = validRecords.find(row =>
      row.series_key.toLowerCase() === seriesKey.toLowerCase() ||
      (commodityId && row.commodity_id === commodityId)
    );

    if (!record) {
      record = validRecords.find(row =>
        row.category?.toLowerCase() === category.toLowerCase() &&
        row.name?.toLowerCase() === name.toLowerCase()
      );
      if (record) tier = 'sibling';
    }

    if (!record) {
      const catRecords = validRecords.filter(row =>
        row.category?.toLowerCase() === category.toLowerCase()
      );
      if (catRecords.length > 0) {
        const totalCovered = catRecords.reduce((sum, r) => sum + r.covered_count, 0);
        const totalSample = catRecords.reduce((sum, r) => sum + r.sample_count, 0);
        const meanHalfWidth = catRecords.reduce((sum, r) => sum + (r.interval_half_width_php ?? 0), 0) / catRecords.length;
        record = {
          model_run_id: loaded?.activeRunId ?? '',
          commodity_id: commodityId ?? '',
          series_key: seriesKey,
          category,
          name,
          variant,
          origin,
          unit,
          forecast_horizon: horizon,
          target_coverage: 95,
          empirical_coverage: (totalCovered / totalSample) * 100,
          covered_count: totalCovered,
          sample_count: totalSample,
          calibration_sample_count: catRecords[0].calibration_sample_count,
          calibration_origin_count: catRecords[0].calibration_origin_count,
          interval_half_width_php: meanHalfWidth,
          calibration_period: catRecords[0].calibration_period,
          evaluation_period: catRecords[0].evaluation_period,
          evaluation_timestamp: catRecords[0].evaluation_timestamp,
          status: 'valid'
        };
        tier = 'category';
      }
    }

    if (!record && validRecords.length > 0) {
      const totalCovered = validRecords.reduce((sum, r) => sum + r.covered_count, 0);
      const totalSample = validRecords.reduce((sum, r) => sum + r.sample_count, 0);
      record = {
        model_run_id: loaded?.activeRunId ?? '',
        commodity_id: commodityId ?? '',
        series_key: seriesKey,
        category,
        name,
        variant,
        origin,
        unit,
        forecast_horizon: horizon,
        target_coverage: 95,
        empirical_coverage: (totalCovered / totalSample) * 100,
        covered_count: totalCovered,
        sample_count: totalSample,
        calibration_sample_count: validRecords[0].calibration_sample_count,
        calibration_origin_count: validRecords[0].calibration_origin_count,
        interval_half_width_php: null,
        calibration_period: validRecords[0].calibration_period,
        evaluation_period: validRecords[0].evaluation_period,
        evaluation_timestamp: validRecords[0].evaluation_timestamp,
        status: 'valid'
      };
      tier = 'horizon';
    }

    if (!record) {
      const reg = await approvedConfidenceRegistry();
      const found = reg.find((r): r is PicpAdmittedConfidence => r.method === 'out_of_sample_picp'
        && r.forecast_horizon === horizon
        && (r.series_key.toLowerCase() === seriesKey.toLowerCase() || (!commodityId || r.commodity_id === commodityId)));
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

    const rawValue = record?.empirical_coverage ?? null;
    const value = (record && Number.isInteger(record.sample_count) && Number.isInteger(record.covered_count) && record.sample_count > 0)
      ? realisticPicpConfidence(record.covered_count, record.sample_count)
      : (rawValue != null ? Math.min(98.5, rawValue) : null);

    let details = 'Historical prediction interval coverage unavailable.';
    if (value != null && record) {
      if (tier === 'exact') {
        details = `Historical prediction interval coverage: ${value.toFixed(1)}% (${record.covered_count}/${record.sample_count} observations inside prediction intervals).`;
      } else if (tier === 'sibling') {
        details = `Historical prediction interval coverage: ${value.toFixed(1)}% (${record.covered_count}/${record.sample_count} observations inside prediction intervals; benchmarked via peer variant).`;
      } else if (tier === 'category') {
        details = `Historical prediction interval coverage: ${value.toFixed(1)}% (${category} sector benchmark from evaluated commodities).`;
      } else {
        details = `Historical prediction interval coverage: ${value.toFixed(1)}% (forecast horizon benchmark).`;
      }
    }

    return Response.json({
      scope: 'historical-picp',
      context,
      evidence: value == null ? {
        kind: 'unavailable',
        value: null,
        label: 'Historical PICP',
        details: 'Historical PICP unavailable.'
      } : {
        kind: 'historicalpicp',
        value,
        label: 'Historical PICP',
        details,
        evidenceId: `picp:${record?.model_run_id || loaded?.activeRunId}:${record?.commodity_id}:${record?.forecast_horizon}:${record?.target_coverage}`
      }
    }, { headers: { 'Cache-Control': 'no-store' } });
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
