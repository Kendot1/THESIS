-- Repair publish_forecast_run for projects that enforce DELETE predicates.
-- This migration changes only the function body; it does not publish a run.
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
