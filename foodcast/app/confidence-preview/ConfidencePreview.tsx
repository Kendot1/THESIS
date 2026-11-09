"use client";
import {useState} from 'react';
import Link from 'next/link';
import ForecastConfidenceBadge from '../components/ForecastConfidenceBadge';
import {rollingPeriods} from '../lib/rolling-periods';
import {encryptId} from '../../lib/idCipher';
type Identity={id:string;name:string;category:string;variant:string;origin:string;unit:string};
export default function ConfidencePreview({products,metadata}:{products:Identity[];metadata:{contractId:string;forecastOrigin:string;modelOrigin:string;modelId:string}}){
 const [id,setId]=useState(products.find(p=>p.name==='Baguio Beans')?.id??products[0].id);
 const [horizon,setHorizon]=useState('daily');
 const p=products.find(p=>p.id===id)!;
 const period=rollingPeriods(metadata.forecastOrigin)[horizon as 'daily'|'weekly'|'monthly'][0];
 const bridge=Math.round((Date.parse(metadata.forecastOrigin)-Date.parse(metadata.modelOrigin))/86400000);
 return <main className="mx-auto max-w-2xl space-y-5 p-5 text-gray-900"><h1 className="text-xl font-bold">Forecast confidence</h1>
 <p className="text-sm">Actual frozen daily-model path. No approved current confidence is available; historical accuracy is separate.</p>
 <label className="block">Product<select aria-label="Product" className="block w-full border p-2" value={id} onChange={e=>setId(e.target.value)}>{products.map(p=><option key={p.id} value={p.id}>{p.name} · {p.variant} · {p.origin} · {p.unit}</option>)}</select></label>
 <label className="block">Horizon<select aria-label="Horizon" className="block w-full border p-2" value={horizon} onChange={e=>setHorizon(e.target.value)}>{['daily','weekly','monthly'].map(h=><option key={h}>{h}</option>)}</select></label>
 <section className="rounded-xl border bg-white p-4"><ForecastConfidenceBadge context={{category:p.category,name:p.name,variant:p.variant,origin:p.origin,unit:p.unit,...metadata,route:'model',horizon,lead:1,targetStart:period.target_start,targetEnd:period.target_end,targetStatistic:horizon==='daily'?'daily_price':horizon==='weekly'?'rolling_7day_mean':'rolling_30day_mean',leadStart:bridge+1,leadEnd:bridge+period.period_days}}/></section>
 <Link className="block underline" href={`/Product/${encryptId(p.id)}?model=incumbent`}>Open actual product forecast</Link><Link className="block underline" href="/accuracy-preview">Separate historical accuracy</Link></main>;
}
