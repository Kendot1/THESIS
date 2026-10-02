-- Keep dashboard history and published predictions on the same unit-aware key.
create or replace function public.dashboard_product_summary(p_since_date date)
returns jsonb
language sql
stable
security invoker
set search_path = pg_catalog
as $$
with history as materialized (
  select f.product_name, f.product_variant, f.origin, f.product_category,
         f.price_index, f.report_date,
         case
           when f.product_category = 'Oils' and lower(f.product_variant) = '1l' then 'liter'
           when f.product_category = 'Oils' and lower(f.product_variant) = '350ml' then '350ml'
           when f.product_name = 'Chicken Egg' then 'piece'
           when lower(trim(coalesce(f.unit, 'unknown'))) in ('per kg', 'kilogram') then 'kg'
           when lower(trim(coalesce(f.unit, 'unknown'))) in ('pc', 'per piece') then 'piece'
           when lower(trim(coalesce(f.unit, 'unknown'))) in ('l', '1 liter', '1l') then 'liter'
           when lower(trim(coalesce(f.unit, 'unknown'))) = '350 ml' then '350ml'
           when lower(trim(coalesce(f.unit, 'unknown'))) = 'milliliter' then 'ml'
           when lower(trim(coalesce(f.unit, 'unknown'))) = 'btl' then 'bottle'
           else lower(trim(coalesce(f.unit, 'unknown')))
         end as unit,
         f.product_name || '|' || coalesce(f.product_variant, '') || '|'
           || coalesce(f.origin, '') || '|' ||
         case
           when f.product_category = 'Oils' and lower(f.product_variant) = '1l' then 'liter'
           when f.product_category = 'Oils' and lower(f.product_variant) = '350ml' then '350ml'
           when f.product_name = 'Chicken Egg' then 'piece'
           when lower(trim(coalesce(f.unit, 'unknown'))) in ('per kg', 'kilogram') then 'kg'
           when lower(trim(coalesce(f.unit, 'unknown'))) in ('pc', 'per piece') then 'piece'
           when lower(trim(coalesce(f.unit, 'unknown'))) in ('l', '1 liter', '1l') then 'liter'
           when lower(trim(coalesce(f.unit, 'unknown'))) = '350 ml' then '350ml'
           when lower(trim(coalesce(f.unit, 'unknown'))) = 'milliliter' then 'ml'
           when lower(trim(coalesce(f.unit, 'unknown'))) = 'btl' then 'bottle'
           else lower(trim(coalesce(f.unit, 'unknown')))
         end as group_key
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
  select p.id, p.name, p.category, p.image_url, p.unit,
         p.name || '|' || coalesce(p.variant, '') || '|'
           || coalesce(p.origin, '') || '|' || coalesce(p.unit, 'unknown') as group_key,
         coalesce(pc.prediction_count, 0) as prediction_count
  from public.products p
  left join prediction_counts pc on pc.product_id = p.id
), resolved as (
  select g.*, m.meta, m.matches, m.product_id as prediction_product_id
  from grouped g
  left join lateral (
    select (array_agg(id))[1] as product_id,
           (jsonb_agg(jsonb_build_object('id', id, 'category', category,
                                         'image_url', image_url)))->0 as meta,
           count(*) as matches
    from metadata where group_key = g.group_key
  ) m on true
), summaries as (
  select r.*, predictions.prices as prediction_prices,
         coalesce(predictions.ambiguous, false) as ambiguous_predictions,
         count(*) over (partition by first_row->>'product_name', first_date,
                        first_row->>'unit') > 1 as ambiguous_group_order
  from resolved r
  left join lateral (
    select jsonb_agg(p.predicted_price order by p.prediction_date) as prices,
           bool_or(p.date_count > 1) as ambiguous
    from (
      select predicted_price, prediction_date,
             count(*) over (partition by prediction_date) as date_count
      from public.predictions
      where product_id = r.prediction_product_id
        and prediction_date > (r.last_row->>'report_date')::date
      order by prediction_date
      limit 7
    ) p
    having min(p.prediction_date) = (r.last_row->>'report_date')::date + 1
       and max(p.prediction_date) - min(p.prediction_date) = count(*)::integer - 1
  ) predictions on true
)
select jsonb_build_object(
  'rows', coalesce(jsonb_agg(jsonb_build_object(
    'first_row', first_row, 'last_row', last_row, 'meta', meta,
    'recent_prices', recent_prices,
    'prediction_prices', coalesce(prediction_prices, '[]'::jsonb)
  ) order by first_date), '[]'::jsonb),
  'requires_legacy', coalesce(bool_or(
    ambiguous_history or matches > 1
    or ambiguous_predictions or ambiguous_group_order), false)
)
from summaries;
$$;

revoke all on function public.dashboard_product_summary(date)
  from public, anon, authenticated;
grant execute on function public.dashboard_product_summary(date) to service_role;

comment on function public.dashboard_product_summary(date) is
  'Unit-aware dashboard scalar inputs with prediction identity parity.';
