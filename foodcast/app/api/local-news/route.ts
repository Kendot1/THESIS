import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { localNewsEnabled, TEST_NEWS_URL } from '../../lib/news-source';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
let anonKey: Promise<string> | undefined;
const newsCache = new Map<string, { payload: unknown; expires: number }>();

// Resolve only the test project's public anon credential. Never serialize keys.
function testAnonKey() {
  const envKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (envKey) return Promise.resolve(envKey);
  return anonKey ??= promisify(execFile)('npx.cmd', [
    '--yes', 'supabase', 'projects', 'api-keys',
    '--remote=zhwhnnxbodzrklhgsurn', '--reveal', '--output', 'json',
  ], { timeout: 90000, windowsHide: true, shell: true }).then(({ stdout }) => {
    const key = JSON.parse(stdout).find((row: { name: string }) => row.name === 'anon')?.api_key;
    if (!key) throw new Error('Anon access unavailable');
    return key as string;
  }).catch(() => { anonKey = undefined; throw new Error('Anon access unavailable'); });
}

export async function GET(request: Request) {
  if (!localNewsEnabled(process.env)) {
    // An optional local bridge is disabled in ordinary development. Avoid an
    // expected 404 in the browser; production remains explicitly unavailable.
    return process.env.NODE_ENV === 'development'
      ? new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } })
      : Response.json({ error: 'Not found' }, { status: 404 });
  }
  const url = new URL(request.url);
  const cacheKey = url.search;
  const now = Date.now();
  const cached = newsCache.get(cacheKey);
  if (cached && cached.expires > now) {
    return Response.json(cached.payload, { headers: { 'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300' } });
  }
  const input = url.searchParams;
  const start = Math.max(0, Math.floor(Number(input.get('start')) || 0));
  const limit = Math.min(1000, Math.max(1, Math.floor(Number(input.get('limit')) || 10)));
  const types = ['supply_shock', 'demand_spike', 'policy_change', 'import_export', 'price_movement', 'weather', 'fuel_energy'];
  const query = new URLSearchParams({
    select: 'id,title,title_tl,content,content_tl,event_type,published_at,published_date,publication_precision,image_url,url,source,sentiment_score,keywords,affected_products',
    event_type: `in.(${types.join(',')})`, affected_products: 'not.is.null',
    and: '(affected_products.neq.{},or(url.like.https://abs-cbn.com/*,url.like.https://*.abs-cbn.com/*,url.like.http://abs-cbn.com/*,url.like.http://*.abs-cbn.com/*))', order: 'published_at.desc.nullslast,id.asc',
    offset: String(start), limit: String(limit),
  });
  const category = input.get('category');
  if (category && category !== 'All') {
    if (!types.includes(category)) return Response.json({ data: [], count: 0 });
    query.set('event_type', `eq.${category}`);
  }
  const search = input.get('search')?.slice(0, 200).replace(/[^\p{L}\p{N}\s-]/gu, ' ').trim();
  if (search) query.set('or', `(title.ilike.*${search}*,content.ilike.*${search}*,source.ilike.*${search}*)`);
  const dateFilter = input.get('dateFilter');
  if (dateFilter === 'Today' || dateFilter === 'Recent') {
    query.set('published_at', `gte.${new Date(Date.now() - (dateFilter === 'Today' ? 1 : 30) * 86400000).toISOString()}`);
  }
  try {
    const key = await testAnonKey();
    const response = await fetch(`${TEST_NEWS_URL}/rest/v1/news_articles?${query}`, {
      method: 'GET', headers: { apikey: key, Authorization: `Bearer ${key}`, Prefer: 'count=exact' },
      cache: 'no-store', signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error('News read failed');
    const resultPayload = { data: await response.json(), count: Number(response.headers.get('content-range')?.split('/')[1] || 0), project_ref: 'zhwhnnxbodzrklhgsurn' };
    newsCache.set(cacheKey, { payload: resultPayload, expires: Date.now() + 60_000 });
    return Response.json(resultPayload, { headers: { 'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300' } });
  } catch {
    return Response.json({ error: 'Test news read unavailable' }, { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
}
