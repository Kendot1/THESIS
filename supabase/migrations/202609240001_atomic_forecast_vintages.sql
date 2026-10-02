-- Immutable forecast vintages and one-transaction publication.
alter table public.products
  add column if not exists unit text not null default 'unknown';

-- Backfill only unambiguous existing product rows. Ambiguous unit identities are
-- intentionally left as unknown and will stop publication until curated.
with normalized_prices as (
  select product_category, product_name,
         coalesce(nullif(product_variant, ''), 'Standard') as variant,
         coalesce(nullif(origin, ''), 'Unknown') as origin,
         case lower(trim(coalesce(unit, 'unknown')))
           when 'per kg' then 'kg' when 'kilogram' then 'kg'
           when 'pc' then 'piece' when 'per piece' then 'piece'
           when 'l' then 'liter' when '1 liter' then 'liter' when '1l' then 'liter'
           when '350 ml' then '350ml' when 'milliliter' then 'ml'
           when 'btl' then 'bottle'
           else lower(trim(coalesce(unit, 'unknown')))
         end as unit
  from public.food_prices
), unambiguous as (
  select product_category, product_name, variant, origin, min(unit) as unit
  from normalized_prices
  group by product_category, product_name, variant, origin
  having count(distinct unit) = 1
)
update public.products p set unit = u.unit
from unambiguous u
where p.category = u.product_category and p.name = u.product_name
  and coalesce(nullif(p.variant, ''), 'Standard') = u.variant
  and coalesce(nullif(p.origin, ''), 'Unknown') = u.origin
  and p.unit = 'unknown';

update public.products set unit = 'liter'
where category = 'Oils' and lower(variant) = '1l';
update public.products set unit = '350ml'
where category = 'Oils' and lower(variant) = '350ml';
update public.products set unit = 'piece'
where name = 'Chicken Egg';

alter table public.products
  drop constraint if exists unique_product_series;
-- Some projects received this constraint manually before migration history was
-- recorded. PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so guard against
-- both an existing constraint and its backing relation/index name.
do $$
begin
  if to_regclass('public.unique_product_series_unit') is null then
    alter table public.products
      add constraint unique_product_series_unit
      unique (name, variant, origin, unit);
  end if;
end
$$;

insert into public.products(name, variant, origin, category, unit)
select distinct
  product_name,
  coalesce(nullif(product_variant, ''), 'Standard'),
  coalesce(nullif(origin, ''), 'Unknown'),
  product_category,
  case
    when product_category = 'Oils' and lower(product_variant) = '1l' then 'liter'
    when product_category = 'Oils' and lower(product_variant) = '350ml' then '350ml'
    when product_name = 'Chicken Egg' then 'piece'
    when lower(trim(coalesce(unit, 'unknown'))) in ('per kg', 'kilogram') then 'kg'
    when lower(trim(coalesce(unit, 'unknown'))) in ('pc', 'per piece') then 'piece'
    when lower(trim(coalesce(unit, 'unknown'))) in ('l', '1 liter', '1l') then 'liter'
    when lower(trim(coalesce(unit, 'unknown'))) = '350 ml' then '350ml'
    when lower(trim(coalesce(unit, 'unknown'))) = 'milliliter' then 'ml'
    when lower(trim(coalesce(unit, 'unknown'))) = 'btl' then 'bottle'
    else lower(trim(coalesce(unit, 'unknown')))
  end
from public.food_prices
where product_name is not null and product_category is not null
on conflict (name, variant, origin, unit) do nothing;

create table if not exists public.forecast_runs (
  id uuid primary key,
  model_run_id text not null,
  generated_at timestamptz not null,
  horizon integer not null check (horizon between 1 and 30),
  row_count integer not null check (row_count > 0),
  created_at timestamptz not null default now()
);

create table if not exists public.forecast_values (
  run_id uuid not null references public.forecast_runs(id) on delete cascade,
  product_id uuid not null references public.products(id),
  prediction_date date not null,
  predicted_price double precision not null check (predicted_price > 0),
  lower_bound double precision not null check (lower_bound > 0),
  upper_bound double precision not null,
  primary key (run_id, product_id, prediction_date),
  check (lower_bound <= predicted_price and predicted_price <= upper_bound)
);

alter table public.forecast_runs enable row level security;
alter table public.forecast_values enable row level security;

drop policy if exists "Anon write predictions" on public.predictions;
drop policy if exists "Service write forecast runs" on public.forecast_runs;
drop policy if exists "Service write forecast values" on public.forecast_values;
create policy "Service write forecast runs" on public.forecast_runs
  for all to service_role using (true) with check (true);
create policy "Service write forecast values" on public.forecast_values
  for all to service_role using (true) with check (true);

create or replace function public.publish_forecast_run(
  p_run_id uuid,
  p_model_run_id text,
  p_generated_at timestamptz,
  p_horizon integer,
  p_rows jsonb
) returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted_count integer;
begin
  if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
    raise exception 'A nonempty forecast array is required';
  end if;

  insert into forecast_runs(id, model_run_id, generated_at, horizon, row_count)
  values (p_run_id, p_model_run_id, p_generated_at, p_horizon, jsonb_array_length(p_rows));

  insert into forecast_values(
    run_id, product_id, prediction_date, predicted_price, lower_bound, upper_bound)
  select p_run_id, x.product_id, x.prediction_date, x.predicted_price,
         x.lower_bound, x.upper_bound
  from jsonb_to_recordset(p_rows) as x(
    product_id uuid,
    prediction_date date,
    predicted_price double precision,
    lower_bound double precision,
    upper_bound double precision
  );
  get diagnostics inserted_count = row_count;
  if inserted_count <> jsonb_array_length(p_rows) then
    raise exception 'Forecast row-count mismatch';
  end if;

  -- Supabase projects with safe-update enforcement reject DELETE without a
  -- syntactic predicate. ctid is non-null for every physical table row.
  delete from predictions where ctid is not null;
  insert into predictions(product_id, prediction_date, predicted_price, lower_bound, upper_bound)
  select product_id, prediction_date, predicted_price, lower_bound, upper_bound
  from forecast_values where run_id = p_run_id;

  return inserted_count;
end;
$$;

revoke all on function public.publish_forecast_run(
  uuid, text, timestamptz, integer, jsonb) from public, anon, authenticated;
grant execute on function public.publish_forecast_run(
  uuid, text, timestamptz, integer, jsonb) to service_role;
