import { headers } from 'next/headers';
import { notFound } from 'next/navigation';
import savedRows from './saved-predictions.json';
import freshRows from './fresh-predictions.json';
const rows = [...freshRows, ...savedRows.filter(r => !freshRows.some(f => f.series === r.series && f.forecast_origin === r.forecast_origin))];
import JuneLayout from './JuneLayout';
import { fetchProducts } from '../lib/data';
export const dynamic = 'force-dynamic';
export default async function Page() {
 const host = (await headers()).get('host') ?? '';
 if (process.env.NODE_ENV !== 'development' || !/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)) notFound();
 return <JuneLayout rows={rows} products={await fetchProducts()} />;
}
