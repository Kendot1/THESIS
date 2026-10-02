-- Store the active model's frozen-holdout quality metrics alongside each
-- published forecast vintage so the UI can report measured, versioned quality.
alter table public.forecast_runs
  add column if not exists metrics jsonb;

create or replace function public.publish_forecast_run_with_metrics(
  p_run_id uuid,
  p_model_run_id text,
  p_generated_at timestamptz,
  p_horizon integer,
  p_rows jsonb,
  p_metrics jsonb
) returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted_count integer;
begin
  inserted_count := public.publish_forecast_run(
    p_run_id, p_model_run_id, p_generated_at, p_horizon, p_rows);

  update public.forecast_runs
  set metrics = p_metrics
  where id = p_run_id;

  if not found then
    raise exception 'Published forecast run was not found for metrics update';
  end if;

  return inserted_count;
end;
$$;

revoke all on function public.publish_forecast_run_with_metrics(
  uuid, text, timestamptz, integer, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.publish_forecast_run_with_metrics(
  uuid, text, timestamptz, integer, jsonb, jsonb) to service_role;
