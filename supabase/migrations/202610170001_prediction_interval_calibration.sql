-- Add interval persistence without rewriting historical predictions.
begin;
alter table public.forecast_values
  add column if not exists interval_level double precision,
  add column if not exists interval_width double precision,
  add column if not exists interval_reliability text;

alter table public.forecast_values
  drop constraint if exists forecast_values_interval_bounds_check,
  drop constraint if exists forecast_values_interval_level_check;
alter table public.forecast_values
  add constraint forecast_values_interval_bounds_check
    check ((lower_bound is null and upper_bound is null
            and interval_level is null and interval_width is null
            and interval_reliability is null)
       or (lower_bound is not null and upper_bound is not null
           and lower_bound > 0 and upper_bound >= lower_bound
           and interval_width is not null and interval_width >= 0
           and interval_level is not null)) not valid,
  add constraint forecast_values_interval_level_check
    check (interval_level is null or (interval_level > 0 and interval_level < 1)) not valid;

create or replace function public.publish_forecast_run(
  p_run_id uuid, p_model_run_id text, p_generated_at timestamptz,
  p_horizon integer, p_rows jsonb
) returns integer
language plpgsql security definer set search_path = public
as $$
declare inserted_count integer;
begin
  if jsonb_typeof(p_rows) is distinct from 'array' or jsonb_array_length(p_rows) = 0 then
    raise exception 'A nonempty forecast array is required';
  end if;
  insert into forecast_runs(id, model_run_id, generated_at, horizon, row_count)
  values (p_run_id, p_model_run_id, p_generated_at, p_horizon, jsonb_array_length(p_rows));
  insert into forecast_values(
    run_id, product_id, prediction_date, predicted_price, forecast_horizon,
    forecast_origin_date, target_period_start, target_period_end, forecast_step,
    confidence_score, confidence_level, covered_days, period_days,
    lower_bound, upper_bound, interval_level, interval_width, interval_reliability)
  select p_run_id, x.product_id, x.prediction_date, x.predicted_price, x.forecast_horizon,
    x.forecast_origin_date, x.target_period_start, x.target_period_end, x.forecast_step,
    x.confidence_score, coalesce(x.confidence_level, 'Insufficient data'),
    x.covered_days, x.period_days, x.lower_bound, x.upper_bound,
    x.interval_level, x.interval_width, x.interval_reliability
  from jsonb_to_recordset(p_rows) as x(
    product_id uuid, prediction_date date, predicted_price double precision,
    forecast_horizon text, forecast_origin_date date, target_period_start date,
    target_period_end date, forecast_step integer, confidence_score double precision,
    confidence_level text, covered_days integer, period_days integer,
    lower_bound double precision, upper_bound double precision,
    interval_level double precision, interval_width double precision, interval_reliability text);
  get diagnostics inserted_count = row_count;
  if inserted_count <> jsonb_array_length(p_rows) then
    raise exception 'Forecast row-count mismatch';
  end if;
  delete from predictions where ctid is not null;
  insert into predictions(product_id, prediction_date, predicted_price)
  select product_id, prediction_date, predicted_price from forecast_values
  where run_id = p_run_id and forecast_horizon = 'daily';
  return inserted_count;
end;
$$;
revoke all on function public.publish_forecast_run(uuid, text, timestamptz, integer, jsonb)
  from public, anon, authenticated;
grant execute on function public.publish_forecast_run(uuid, text, timestamptz, integer, jsonb)
  to service_role;
notify pgrst, 'reload schema';
commit;
