export const TEST_NEWS_URL = 'https://zhwhnnxbodzrklhgsurn.supabase.co';
export function localNewsEnabled(env: Record<string, string | undefined>): boolean {
  return env.NODE_ENV === 'development' && env.FOODCAST_LOCAL_READ_ONLY === '1';
}

/** Show only articles whose canonical URL host belongs to ABS-CBN. */
export function isAbsCbnArticle(article: { url?: string | null }): boolean {
  try {
    const url = new URL(article.url ?? '');
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    return (url.protocol === 'https:' || url.protocol === 'http:')
      && (host === 'abs-cbn.com' || host.endsWith('.abs-cbn.com'));
  } catch {
    return false;
  }
}
