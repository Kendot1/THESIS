-- Keep source publication timing distinct from ingestion time. Existing records
-- remain unverified by default; they must not be used as historical vintages.
alter table public.news_articles
  add column if not exists published_date date,
  add column if not exists publication_precision text not null default 'unknown',
  add column if not exists publication_source text not null default 'unknown';

alter table public.news_articles
  alter column published_at drop not null;

alter table public.news_articles
  add constraint news_articles_publication_precision_check
    check (publication_precision in ('timestamp', 'date', 'unknown')) not valid,
  add constraint news_articles_publication_source_check
    check (publication_source in (
      'crawler_metadata', 'article_published_meta', 'json_ld_date_published',
      'url_date', 'unknown'
    )) not valid;

comment on column public.news_articles.published_at is
  'Source publication timestamp with explicit timezone; null unless exact timing is known.';
comment on column public.news_articles.published_date is
  'Source publication date when known, including date-only sources; date-only signals require a conservative one-day availability delay.';
comment on column public.news_articles.created_at is
  'Ingestion time. Never use as source publication time in historical model features.';
