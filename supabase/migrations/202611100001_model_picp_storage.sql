-- Archive measured PICP separately from forecast probability/approval.
begin;
create table if not exists public.model_confidence_evaluations (
  model_run_id text not null,
  commodity_id uuid not null,
  forecast_horizon text not null check (forecast_horizon in ('daily','weekly','monthly')),
  target_coverage double precision not null check (target_coverage > 0 and target_coverage <= 100),
  empirical_coverage double precision check (empirical_coverage between 0 and 100),
  sample_count integer not null check (sample_count >= 0),
  covered_count integer not null check (covered_count >= 0 and covered_count <= sample_count),
  status text not null,
  evaluation jsonb not null,
  independently_approved boolean not null default false,
  stored_at timestamptz not null default now(),
  primary key(model_run_id, commodity_id, forecast_horizon, target_coverage)
);
alter table public.model_confidence_evaluations enable row level security;
revoke all on public.model_confidence_evaluations from anon, authenticated;
grant select, insert, update on public.model_confidence_evaluations to service_role;
create or replace function public.upsert_model_confidence_evaluations(p_rows jsonb)
returns integer language plpgsql security definer set search_path=public as $$
declare n integer;
begin
  if jsonb_typeof(p_rows) is distinct from 'array' then
    raise exception 'PICP records must be an array';
  end if;
  insert into model_confidence_evaluations(
    model_run_id,commodity_id,forecast_horizon,target_coverage,empirical_coverage,
    sample_count,covered_count,status,evaluation)
  select r->>'model_run_id',(r->>'commodity_id')::uuid,r->>'forecast_horizon',
    (r->>'target_coverage')::double precision,(r->>'empirical_coverage')::double precision,
    (r->>'sample_count')::integer,(r->>'covered_count')::integer,r->>'status',r
  from jsonb_array_elements(p_rows) r
  on conflict(model_run_id,commodity_id,forecast_horizon,target_coverage) do update set
    empirical_coverage=excluded.empirical_coverage,sample_count=excluded.sample_count,
    covered_count=excluded.covered_count,status=excluded.status,evaluation=excluded.evaluation,
    independently_approved=false,stored_at=now();
  get diagnostics n=row_count;
  return n;
end; $$;
revoke all on function public.upsert_model_confidence_evaluations(jsonb) from public,anon,authenticated;
grant execute on function public.upsert_model_confidence_evaluations(jsonb) to service_role;
notify pgrst,'reload schema';
commit;
