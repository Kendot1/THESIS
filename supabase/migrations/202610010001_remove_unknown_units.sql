-- Remove legacy unit-less data and reject it at ingestion going forward.
create temporary table unknown_product_ids on commit drop as
select id from public.products
where lower(trim(unit)) = 'unknown' or trim(unit) = '';

delete from public.predictions
where product_id in (select id from unknown_product_ids);

delete from public.forecast_values
where product_id in (select id from unknown_product_ids);

delete from public.product_daily_views
where product_id in (select id::text from unknown_product_ids);

delete from public.products
where id in (select id from unknown_product_ids);

delete from public.food_prices
where unit is null or trim(unit) = '' or lower(trim(unit)) = 'unknown';

alter table public.food_prices
  alter column unit set not null;

alter table public.food_prices
  drop constraint if exists food_prices_known_unit;
alter table public.food_prices
  add constraint food_prices_known_unit
  check (trim(unit) <> '' and lower(trim(unit)) <> 'unknown');

alter table public.products
  alter column unit drop default;

alter table public.products
  drop constraint if exists products_known_unit;
alter table public.products
  add constraint products_known_unit
  check (trim(unit) <> '' and lower(trim(unit)) <> 'unknown');
