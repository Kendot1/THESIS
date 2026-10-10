-- Persist complete daily, calendar-week, and calendar-month point sequences.
-- Weekly/monthly prices are means of the daily model path within each target
-- period; partial edge periods retain both covered and calendar day counts.
-- Keep legacy interval values for historical rows, but make the old columns
-- nullable so new point-only publications do not need to fabricate bounds.
alter table public.forecast_values
  add column if not exists forecast_horizon text,
  add column if not exists forecast_origin_date date,
  add column if not exists target_period_start date,
  add column if not exists target_period_end date,
  add column if not exists forecast_step integer,
  add column if not exists confidence_score double precision,
  add column if not exists confidence_level text,
  add column if not exists covered_days integer,
  add column if not exists period_days integer;

with ranked as (
  select fv.run_id, fv.product_id, fv.prediction_date,
         row_number() over (partition by fv.run_id, fv.product_id
                            order by fv.prediction_date) as step,
         (fr.generated_at at time zone 'Asia/Manila')::date as origin
  from public.forecast_values fv
  join public.forecast_runs fr on fr.id = fv.run_id
)
update public.forecast_values fv
set forecast_horizon = coalesce(fv.forecast_horizon, 'daily'),
    forecast_origin_date = coalesce(fv.forecast_origin_date, ranked.origin),
    target_period_start = coalesce(fv.target_period_start, fv.prediction_date),
    target_period_end = coalesce(fv.target_period_end, fv.prediction_date),
    forecast_step = coalesce(fv.forecast_step, ranked.step::integer),
    confidence_level = coalesce(fv.confidence_level, 'Insufficient data'),
    covered_days = coalesce(fv.covered_days, 1),
    period_days = coalesce(fv.period_days, 1)
from ranked
where fv.run_id = ranked.run_id
  and fv.product_id = ranked.product_id
  and fv.prediction_date = ranked.prediction_date;

alter table public.forecast_values
  alter column lower_bound drop not null,
  alter column upper_bound drop not null,
  alter column forecast_horizon set not null,
  alter column forecast_origin_date set not null,
  alter column target_period_start set not null,
  alter column target_period_end set not null,
  alter column forecast_step set not null,
  alter column confidence_level set not null,
  alter column covered_days set not null,
  alter column period_days set not null;

alter table public.forecast_values
  drop constraint if exists forecast_values_pkey,
  drop constraint if exists forecast_values_check,
  drop constraint if exists forecast_values_lower_bound_check,
  drop constraint if exists forecast_values_upper_bound_check,
  drop constraint if exists forecast_values_horizon_check,
  drop constraint if exists forecast_values_step_check,
  drop constraint if exists forecast_values_confidence_score_check,
  drop constraint if exists forecast_values_confidence_level_check,
  drop constraint if exists forecast_values_period_check;

alter table public.forecast_values
  add constraint forecast_values_pkey
    primary key (run_id, product_id, forecast_horizon, forecast_step),
  add constraint forecast_values_horizon_check
    check (forecast_horizon in ('daily', 'weekly', 'monthly')),
  add constraint forecast_values_step_check check (forecast_step > 0),
  add constraint forecast_values_confidence_score_check
    check (confidence_score is null or confidence_score between 0 and 100),
  add constraint forecast_values_confidence_level_check
    check (confidence_level in ('Very High', 'High', 'Moderate', 'Low', 'Very Low', 'Insufficient data')),
  add constraint forecast_values_period_check
    check (target_period_start <= target_period_end
       and covered_days > 0 and period_days >= covered_days);

alter table public.predictions
  alter column lower_bound drop not null,
  alter column upper_bound drop not null;

create index if not exists forecast_values_run_horizon_product_step_idx
  on public.forecast_values(run_id, forecast_horizon, product_id, forecast_step);

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
    run_id, product_id, prediction_date, predicted_price, forecast_horizon,
    forecast_origin_date, target_period_start, target_period_end, forecast_step,
    confidence_score, confidence_level, covered_days, period_days)
  select p_run_id, x.product_id, x.prediction_date, x.predicted_price,
         x.forecast_horizon, x.forecast_origin_date, x.target_period_start,
         x.target_period_end, x.forecast_step, x.confidence_score,
         coalesce(x.confidence_level, 'Insufficient data'),
         x.covered_days, x.period_days
  from jsonb_to_recordset(p_rows) as x(
    product_id uuid,
    prediction_date date,
    predicted_price double precision,
    forecast_horizon text,
    forecast_origin_date date,
    target_period_start date,
    target_period_end date,
    forecast_step integer,
    confidence_score double precision,
    confidence_level text,
    covered_days integer,
    period_days integer
  );
  get diagnostics inserted_count = row_count;
  if inserted_count <> jsonb_array_length(p_rows) then
    raise exception 'Forecast row-count mismatch';
  end if;

  delete from predictions where ctid is not null;
  insert into predictions(product_id, prediction_date, predicted_price)
  select product_id, prediction_date, predicted_price
  from forecast_values
  where run_id = p_run_id and forecast_horizon = 'daily';

  return inserted_count;
end;
$$;

revoke all on function public.publish_forecast_run(
  uuid, text, timestamptz, integer, jsonb) from public, anon, authenticated;
grant execute on function public.publish_forecast_run(
  uuid, text, timestamptz, integer, jsonb) to service_role;
