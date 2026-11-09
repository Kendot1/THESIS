-- Read only evaluation evidence for the latest published model; no write access.
create or replace function public.read_model_confidence_evaluations()
returns jsonb language sql stable security definer set search_path=public
as $$
 select jsonb_build_object(
   'model_run_id', latest.model_run_id,
   'records', coalesce((select jsonb_agg(jsonb_build_object(
     'evaluation', e.evaluation, 'independently_approved', e.independently_approved))
     from public.model_confidence_evaluations e
     where e.model_run_id=latest.model_run_id), '[]'::jsonb))
 from (select model_run_id from public.forecast_runs
       order by generated_at desc,id desc limit 1) latest;
$$;
revoke all on function public.read_model_confidence_evaluations() from public;
grant execute on function public.read_model_confidence_evaluations() to anon,authenticated,service_role;
notify pgrst,'reload schema';
