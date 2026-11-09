import {headers} from 'next/headers';
import {notFound} from 'next/navigation';
import {readFile} from 'node:fs/promises';
import {readDailyAverage} from '../lib/local-rolling';
import ConfidencePreview from './ConfidencePreview';
export const dynamic='force-dynamic';
export default async function Page(){
 const host=(await headers()).get('host')?.split(':')[0];
 if(process.env.NODE_ENV!=='development'||!['localhost','127.0.0.1'].includes(host??''))notFound();
 const catalog=JSON.parse(await readFile('D:/THESIS/audits/rolling_tomorrow_20261109/products.json','utf8'));
 // Reader hash-verifies catalog, manifest and actual frozen daily path.
 const sample=await readDailyAverage(catalog[0].id);
 return <ConfidencePreview products={catalog} metadata={{contractId:sample.contract,forecastOrigin:sample.forecast_origin,modelOrigin:sample.model_origin,modelId:sample.model_run}}/>;
}
