-- Forecast publication stores the generated path length in forecast_runs.horizon.
-- Daily publication now writes a 90-day path, so the original 30-day ceiling
-- must be widened before the atomic publisher can accept the new vintage.
alter table public.forecast_runs
  drop constraint if exists forecast_runs_horizon_check;

alter table public.forecast_runs
  add constraint forecast_runs_horizon_check
  check (horizon between 1 and 90);
