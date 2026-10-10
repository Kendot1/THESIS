-- Three calendar months can span up to 122 forecast days when the origin is
-- at the start of a month and the target month has 31 days.
alter table public.forecast_runs
  drop constraint if exists forecast_runs_horizon_check;

alter table public.forecast_runs
  add constraint forecast_runs_horizon_check
  check (horizon between 1 and 122);
