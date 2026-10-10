-- Forecast publication inserts a complete multi-horizon vintage in one
-- transaction. Give only these publication functions the documented maximum
-- PostgREST API execution window; normal API queries keep their timeout.
alter function public.publish_forecast_run(
  uuid, text, timestamptz, integer, jsonb
) set statement_timeout = '60s';

alter function public.publish_forecast_run_with_metrics(
  uuid, text, timestamptz, integer, jsonb, jsonb
) set statement_timeout = '60s';

notify pgrst, 'reload schema';
