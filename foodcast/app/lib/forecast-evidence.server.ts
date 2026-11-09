import 'server-only';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {parseCsv} from './historical-performance.server';
import type {HistoricalAccuracy} from './forecast-evidence';
import type {ProductAccuracy} from './product-accuracy';
const apiHash='0b123f94bb35944390e8de6747a6589d4d6a60f945aa74f148cbab1aaffae863';
const sourceHash='451a5aaae58adf29e3fe30726bdbc36c5244e3fd43001621c2a35237dabd4a31';
const digest=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
/** Recompute the approved descriptive historical metric, never infer it from an arbitrary MAPE field.
 * No confidence profiles are loaded. Archived original contract only, not current rolling forecasts. */
export async function verifiedHistoricalEvidence():Promise<HistoricalAccuracy[]> {
 try {
  const api=await readFile(path.resolve(process.cwd(),'../audits/product_accuracy_v1/results/PRODUCT_ACCURACY_API.json'));
  const bytes=await readFile(path.resolve(process.cwd(),'../audits/accuracy_goal_20261021/defense_improvement_batch/daily7/saved_predictions.csv'));
  if(digest(api)!==apiHash||digest(bytes)!==sourceHash)return [];
  const artifact=JSON.parse(api.toString('utf8')) as {products:ProductAccuracy[];product_leads:ProductAccuracy[]};
  const [header,...data]=parseCsv(bytes.toString('utf8'));const index=(name:string)=>{const i=header.indexOf(name);if(i<0)throw Error('column');return i;};
  const s=index('series'),a=index('actual'),p=index('incumbent_served'),l=index('lead'),h=index('horizon_name'),t=index('target_end');
  const seen=new Set<string>();const keyIndexes=['series','forecast_origin','target_start','target_end','lead'].map(index);
  for(const row of data){const key=JSON.stringify(keyIndexes.map(i=>row[i]));if(seen.has(key)||row[h]!=='daily_7d'||row.length!==header.length)throw Error('invalid original grid');seen.add(key);}
  const result:HistoricalAccuracy[]=[];
  for(const row of [...artifact.products,...artifact.product_leads]){
   if(row.horizon!=='daily'||row.model_id!=='20261001T025925Z_0661960a:incumbent_served'||row.contract_id!=='historical_archived_daily14_leads1_to7')continue;
   const pairs=data.filter(r=>r[s]===row.series&&(row.lead==null||Number(r[l])===row.lead)&&r[a].trim()!==''&&r[p].trim()!==''&&Number.isFinite(Number(r[a]))&&Number(r[a])>=1e-8&&Number.isFinite(Number(r[p]))&&Number(r[p])>=0);
   if(!pairs.length)continue;
   const value=pairs.reduce((sum,r)=>sum+(1-Math.abs(Number(r[a])-Number(r[p]))/Number(r[a]))*100,0)/pairs.length;
   if(row.historical_relative_accuracy_pct==null||Math.abs(value-row.historical_relative_accuracy_pct)>1e-8||pairs.length!==row.evaluated_predictions)continue;
   const dates=pairs.map(r=>r[t]).sort();
   result.push({category:row.product_category,name:row.product_name,variant:row.product_variant,origin:row.origin,unit:row.unit,modelId:row.model_id,route:'incumbent_served',contractId:row.contract_id,horizon:row.horizon,lead:row.lead,evidenceId:`${sourceHash}:${row.series}:lead=${row.lead??'all'}`,verified:true,forecast_accuracy_pct:value,n:pairs.length,periodStart:dates[0],periodEnd:dates[dates.length-1],formula:'mean_relative_accuracy'});
  }
  return result;
 } catch {return [];}
}
