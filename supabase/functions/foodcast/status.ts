/** Read published evaluation metadata without scoring live price outcomes. */
export async function loadForecastStatus(supabase: any) {
  const latest = (columns: string) => supabase.from("forecast_runs")
    .select(columns)
    .order("generated_at", { ascending: false })
    .order("id", { ascending: false })
    .limit(1).maybeSingle();

  let response = await latest("model_run_id, generated_at, horizon, row_count, metrics");
  // Support the additive metrics migration without hiding unrelated failures.
  if (response.error?.code === "42703" && /\bmetrics\b/.test(response.error.message)) {
    response = await latest("model_run_id, generated_at, horizon, row_count");
  }
  if (response.error) throw response.error;
  if (!response.data) return null;

  const run = response.data;
  const metrics = run.metrics && typeof run.metrics === "object" && !Array.isArray(run.metrics)
    ? run.metrics : null;
  // Evaluation belongs to the training/evaluation pipeline. Request-time
  // scoring would be expensive and could consume reserved holdout outcomes.
  return {
    modelRunId: run.model_run_id,
    generatedAt: run.generated_at,
    horizon: run.horizon,
    rowCount: run.row_count,
    metrics,
    modelMetrics: metrics,
  };
}
