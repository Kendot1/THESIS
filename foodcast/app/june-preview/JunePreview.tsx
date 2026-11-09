"use client";
import { useState } from 'react';
type Row = { series: string; forecast_origin: string; target_date: string; step: number; prediction: number; actual: number | null };
export default function JunePreview({ rows }: { rows: Row[] }) {
 const products = [...new Set(rows.map(r => r.series))].sort();
 const [series,setSeries] = useState(products[0] ?? '');
 const dates = [...new Set(rows.filter(r => r.series===series).map(r=>r.forecast_origin))].sort();
 const [origin,setOrigin] = useState('');
 const chosen = dates.includes(origin) ? origin : dates[dates.length-1];
 const selected = rows.filter(r=>r.series===series && r.forecast_origin===chosen).sort((a,b)=>a.step-b.step);
 return <main style={{maxWidth:1100,margin:'40px auto',padding:24}}>
 <h1>June LSTM — local saved prediction preview</h1>
 <p>Original frozen June LSTM component · historical next-report steps, not calendar Daily-7. No live inference or production changes.</p>
 <p>Development-reused retrospective evidence. Training/scaler cutoff provenance incomplete. Confidence: Not calibrated.</p>
 <label>Product <select value={series} onChange={e=>setSeries(e.target.value)}>{products.map(s=><option key={s}>{s}</option>)}</select></label>
 <br/><label>Historical forecast origin <select value={chosen ?? ''} onChange={e=>setOrigin(e.target.value)}>{dates.map(d=><option key={d}>{d}</option>)}</select></label>
 <p>The origin is the first unseen report; all inputs precede it. Missing target dates remain unavailable.</p>
 <table style={{width:'100%',marginTop:20}}><thead><tr><th>Report step</th><th>Target report date</th><th>June LSTM prediction</th><th>Recorded actual</th></tr></thead>
 <tbody>{selected.map(r=><tr key={r.step}><td>{r.step}</td><td>{r.target_date || 'Unavailable'}</td><td>₱{r.prediction.toFixed(2)}</td><td>{r.actual==null?'Unavailable':`₱${r.actual.toFixed(2)}`}</td></tr>)}</tbody></table>
 </main>;
}
