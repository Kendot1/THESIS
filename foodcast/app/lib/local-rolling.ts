import 'server-only';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { rollingPeriods, ROLLING_CONTRACT } from './rolling-periods';
import type { StagingForecast } from '../research-model-test/staging';

const ROOT = 'D:/THESIS/audits/local_rolling_hybrid_integration/';
const HASHES = {
  'products.json': '33a20d855457e409a7351afca94dd7fa2d69220daaed14961990e84e59ba7962',
  'forecasts.json': 'caec1bbacbe24cea4f24ab9a0673030887adc8f2857a21081e3df6cbd8c1ac1e',
};
type Identity = { id: string; category: string; name: string; variant: string; origin: string; unit: string };
type Payload = { contract?: string; forecast_origin: string; predictions: StagingForecast[] };
const CONTRACT = 'research_rolling_daily7_weekly4_monthly1_v1';
export function selectRolling(payload: Payload, product?: Identity) {
  const unavailable = (reason: string) => ({ contract: CONTRACT, forecast_origin: payload.forecast_origin, product,
    model: 'June rolling fixed 50/50 independent-price hybrid', source: 'local_immutable_saved_outputs',
    confidence_score: null, metrics: null, predictions: [] as StagingForecast[], unavailable_reason: reason });
  if (!product) return unavailable('Product ID not found in frozen local catalog; no incumbent substitution');
  const key = JSON.stringify([product.category, product.name, product.variant, product.origin, product.unit]);
  const rows = payload.predictions.filter(row => row.series === key &&
    row.product_series.product_category === product.category && row.product_series.product_name === product.name &&
    row.product_series.product_variant === product.variant && row.product_series.origin === product.origin && row.product_series.unit === product.unit);
  if (payload.contract !== CONTRACT || payload.forecast_origin !== '2025-11-28') return unavailable('Unexpected rolling contract or origin');
  const origin = new Date(`${payload.forecast_origin}T00:00:00Z`);
  const day = (offset: number) => { const d = new Date(origin); d.setUTCDate(d.getUTCDate() + offset); return d.toISOString().slice(0, 10); };
  for (const [h, n] of [['daily', 7], ['weekly', 4], ['monthly', 1]] as const) {
    const batch = rows.filter(r => r.horizon === h).sort((a, b) => a.lead - b.lead);
    if (batch.length !== n) return unavailable('No complete exact full-identity 7/4/1 match; no incumbent substitution');
    for (let i = 0; i < n; i++) {
      const r = batch[i];
      const start = h === 'daily' ? day(i + 1) : h === 'weekly' ? day(i * 7 + 1) : day(1);
      const end = h === 'daily' ? day(i + 1) : h === 'weekly' ? day((i + 1) * 7) : '2025-12-28';
      if (r.lead !== i + 1 || r.forecast_origin !== payload.forecast_origin || r.target_start !== start || r.target_end !== end || r.prediction == null || !Number.isFinite(r.prediction) || r.confidence_score !== null)
        return unavailable('Invalid saved period, value or provenance; no incumbent substitution');
    }
  }
  return { ...unavailable(''), predictions: rows, unavailable_reason: null };
}
export async function readFreshRolling(id: string) {
  const root = 'D:/THESIS/audits/fresh_rolling_current_20261109/';
  const hashes = { 'products.json': '33a20d855457e409a7351afca94dd7fa2d69220daaed14961990e84e59ba7962', 'forecasts.json': '83e5d9d3f5f086ebd34a982f150f01707b09d647ead40b4171977ad30619b8eb' };
  const read = async (name: keyof typeof hashes) => {
    const bytes = await readFile(root + name);
    if (createHash('sha256').update(bytes).digest('hex') !== hashes[name]) throw new Error('Fresh inference hash mismatch');
    return JSON.parse(bytes.toString('utf8'));
  };
  const [products, payload] = await Promise.all([read('products.json'), read('forecasts.json')]);
  return selectFreshRolling(payload, (products as Identity[]).find(p => p.id === id));
}
export function selectFreshRolling(payload: Payload, product?: Identity) {
  const unavailable = (reason: string) => ({ contract: 'fresh_rolling_weekly4_monthly1_v1', forecast_origin: payload.forecast_origin, product,
    model: 'June rolling 0.5 LSTM + 0.5 independent LightGBM', source: 'fresh_local_frozen_weight_inference',
    confidence_score: null, metrics: null, predictions: [] as StagingForecast[], unavailable_reason: reason });
  if (!product || payload.contract !== 'fresh_rolling_weekly4_monthly1_v1' || payload.forecast_origin !== '2026-11-09') return unavailable('Invalid fresh contract or identity');
  const key = JSON.stringify([product.category, product.name, product.variant, product.origin, product.unit]);
  const rows = payload.predictions.filter(r => r.series === key && r.product_series.product_category === product.category && r.product_series.product_name === product.name && r.product_series.product_variant === product.variant && r.product_series.origin === product.origin && r.product_series.unit === product.unit);
  const origin = new Date(`${payload.forecast_origin}T00:00:00Z`);
  const day = (offset: number) => { const d = new Date(origin); d.setUTCDate(d.getUTCDate() + offset); return d.toISOString().slice(0, 10); };
  const nextMonth = rollingPeriods(payload.forecast_origin).monthly[0].target_end;
  if (rows.length !== 5) return unavailable('Incomplete fresh 4/1 identity match');
  for (const [h, n] of [['weekly', 4], ['monthly', 1]] as const) {
    const batch = rows.filter(r => r.horizon === h).sort((a, b) => a.lead - b.lead);
    if (batch.length !== n) return unavailable('Incomplete fresh horizon');
    for (let i = 0; i < n; i++) {
      const r = batch[i];
      if (r.lead !== i + 1 || r.forecast_origin !== payload.forecast_origin || r.target_start !== day(h === 'weekly' ? 7 * i + 1 : 1) || r.target_end !== (h === 'weekly' ? day(7 * (i + 1)) : nextMonth) || r.confidence_score !== null || (!r.unavailable && (r.prediction == null || !Number.isFinite(r.prediction)))) return unavailable('Invalid fresh dates, value or uncertainty');
    }
  }
  return { ...unavailable(''), predictions: rows, unavailable_reason: null };
}
export async function readDailyAverageCatalog() {
  const { aggregateDailyPath } = await import('./daily-average');
  const root = 'D:/THESIS/audits/rolling_tomorrow_20261109/';
  const read = async (name: string, hash: string) => {
    const bytes = await readFile(root + name);
    if (createHash('sha256').update(bytes).digest('hex') !== hash) throw new Error('Daily path hash mismatch');
    return JSON.parse(bytes.toString('utf8'));
  };
  const [products, payload, manifest] = await Promise.all([
    read('products.json', '33a20d855457e409a7351afca94dd7fa2d69220daaed14961990e84e59ba7962'),
    read('raw_paths.json', '0e920f9187afd97ee6b4b9deaee9a36b7d1288d9ea00a0281aae62a3fe05adef'),
    read('manifest.json', 'c376bf67d5b96d1ba243daa7f5ce7d864375a3b79fd5146ed9dc5cb9acb65e6d'),
  ]);
  if (payload.forecast_origin !== manifest.forecast_origin || manifest.contract !== ROLLING_CONTRACT || manifest.actual_fits !== 0) throw new Error('Invalid rolling manifest');
  return (products as Identity[]).map(product => {
  const id = product.id;
  const item = payload.paths.find((p: {product_id: string}) => p.product_id === id);
  const base = {contract:ROLLING_CONTRACT, forecast_origin:payload.forecast_origin, model_origin:manifest.model_origin, model:'Daily model average', model_run:payload.model_run, product, source:'frozen_incumbent_daily_path', confidence_score:null, metrics:null};
  if (!product || !item) return {...base, predictions:[], unavailable_reason:payload.unavailable.find((p: {product_id: string}) => p.product_id === id)?.reason ?? 'No complete eligible daily-model path'};
  for (const [a,b] of [['category','product_category'],['name','product_name'],['variant','product_variant'],['origin','origin'],['unit','unit']] as const) if (product[a] !== item.product_series[b]) throw new Error('Identity mismatch');
  if (item.model_run !== '20261001T025925Z_0661960a' || item.forecast_origin !== payload.forecast_origin) throw new Error('Model origin mismatch');
  return {...base, predictions:aggregateDailyPath(payload.forecast_origin,item.path).map(row=>({...row, product_series:item.product_series, series:JSON.stringify(Object.values(item.product_series)), fallback:false, route:'model',confidence_level:'Insufficient data'})), unavailable_reason:null};
  });
}
export async function readDailyAverage(id: string) {
  const item = (await readDailyAverageCatalog()).find(item => item.product.id === id);
  if (!item) throw new Error('Unknown frozen product');
  return item;
}
export async function readLocalRolling(id: string) {
  const read = async (name: keyof typeof HASHES) => {
    const bytes = await readFile(ROOT + name);
    if (createHash('sha256').update(bytes).digest('hex') !== HASHES[name]) throw new Error('Local saved-output hash mismatch');
    return JSON.parse(bytes.toString('utf8'));
  };
  const [products, payload] = await Promise.all([read('products.json'), read('forecasts.json')]);
  const matches = (products as Identity[]).filter(p => p.id === id);
  return selectRolling(payload, matches.length === 1 ? matches[0] : undefined);
}
