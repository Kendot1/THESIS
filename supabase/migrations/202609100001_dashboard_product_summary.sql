-- Additive, read-only summary. Keep JS rounding/regression in the Edge function.
-- One JSON value avoids the PostgREST row cap for catalogs over 1,000 groups.
create or replace function public.dashboard_product_summary(p_since_date date)
returns jsonb
language sql
stable
security invoker
set search_path = pg_catalog
as $$
with history as materialized (
  select f.product_name, f.product_variant, f.origin, f.product_category,
         f.price_index, f.report_date, f.unit,
         f.product_name || '|' || coalesce(f.product_variant, '') || '|' || coalesce(f.origin, '') as group_key
  from public.food_prices f
  where f.report_date >= p_since_date
), ranked as (
  select h.*,
         row_number() over (partition by group_key order by report_date) as rn,
         count(*) over (partition by group_key) as row_count,
         count(*) over (partition by group_key, report_date) as date_count
  from history h
), grouped as (
  select group_key, min(report_date) as first_date,
         (jsonb_agg(to_jsonb(r) - 'group_key' - 'rn' - 'row_count' - 'date_count') filter (where rn = 1))->0 as first_row,
         (jsonb_agg(to_jsonb(r) - 'group_key' - 'rn' - 'row_count' - 'date_count') filter (where rn = row_count))->0 as last_row,
         jsonb_agg(price_index order by rn) filter (where rn > row_count - 7) as recent_prices,
         bool_or(date_count > 1) as ambiguous_history
  from ranked r
  where row_count >= 2
  group by group_key
), prediction_counts as materialized (
  select product_id, count(*) as prediction_count
  from public.predictions
  group by product_id
), metadata as materialized (
  select p.id, p.name, p.category, p.image_url,
         p.name || '|' || coalesce(p.variant, '') || '|' || coalesce(p.origin, '') as group_key,
         coalesce(pc.prediction_count, 0) as prediction_count
  from public.products p
  left join prediction_counts pc on pc.product_id = p.id
), resolved as (
  select g.*, m.meta, m.matches,
         coalesce(m.product_id, fallback.product_id) as prediction_product_id,
         coalesce(fallback.ties, 0) as fallback_ties
  from grouped g
  left join lateral (
    select (array_agg(id))[1] as product_id,
           (jsonb_agg(jsonb_build_object('id', id, 'category', category, 'image_url', image_url)))->0 as meta,
           count(*) as matches
    from metadata where group_key = g.group_key
  ) m on true
  left join lateral (
    select id as product_id, count(*) over (partition by prediction_count) as ties
    from metadata
    where name = g.first_row->>'product_name' and prediction_count > 0
    order by prediction_count desc
    limit 1
  ) fallback on m.matches = 0
), summaries as (
  select r.*, predictions.prices as prediction_prices,
         coalesce(predictions.ambiguous, false) as ambiguous_predictions,
         count(*) over (partition by first_row->>'product_name', first_date) > 1 as ambiguous_group_order
  from resolved r
  left join lateral (
    select jsonb_agg(p.predicted_price order by p.prediction_date) as prices,
           bool_or(p.date_count > 1) as ambiguous
    from (
      select predicted_price, prediction_date,
             count(*) over (partition by prediction_date) as date_count
      from public.predictions
      where product_id = r.prediction_product_id
      order by prediction_date
      limit 7
    ) p
  ) predictions on true
)
select jsonb_build_object(
  'rows', coalesce(jsonb_agg(jsonb_build_object(
    'first_row', first_row, 'last_row', last_row, 'meta', meta,
    'recent_prices', recent_prices, 'prediction_prices', coalesce(prediction_prices, '[]'::jsonb)
  ) order by first_date), '[]'::jsonb),
  -- Legacy queries have no tie breaker. Do not invent one for ambiguous groups.
  'requires_legacy', coalesce(bool_or(ambiguous_history or matches > 1 or fallback_ties > 1
                                     or ambiguous_predictions or ambiguous_group_order), false)
)
from summaries;
$$;

revoke all on function public.dashboard_product_summary(date) from public, anon, authenticated;
grant execute on function public.dashboard_product_summary(date) to service_role;

comment on function public.dashboard_product_summary(date) is
  'Dashboard scalar inputs with <=7 history/prediction prices per group. Service-role Edge access only; ambiguous legacy ordering is flagged.';
