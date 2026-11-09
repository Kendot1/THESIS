export type HistoricalCell = { series: string; model_run_id: string; contract: string; horizon: string; lead: string; route: string; n: number; hits: number; pct: number | null };
/** Descriptive binomial interval, not independent-validation or future calibration. */
export function historicalSummary(cell: HistoricalCell | undefined) {
  if (!cell || !Number.isInteger(cell.n) || cell.n < 20 || !Number.isInteger(cell.hits) || cell.hits < 0 || cell.hits > cell.n || cell.pct == null) return null;
  const n = cell.n, p = cell.hits / n, z = 1.959963984540054;
  const denominator = 1 + z * z / n;
  const center = (p + z * z / (2 * n)) / denominator;
  const radius = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator;
  return { pct: 100 * p, low: 100 * Math.max(0, center - radius), high: 100 * Math.min(1, center + radius), n, hits: cell.hits };
}
/** Descriptive seven-lead score, not seven independent samples per origin.
 * Require support at EACH lead; never let pooled rows manufacture support.
 */
export function dailyModelSummary(cells: HistoricalCell[], series: string, model: string | undefined) {
  const selected: HistoricalCell[] = [];
  for (let lead = 1; lead <= 7; lead++) {
    const matches = matchingHistoricalCells(cells, series, model, 'daily', lead)
      .filter(cell => cell.route === 'model');
    if (matches.length !== 1 || !historicalSummary(matches[0])) return null;
    selected.push(matches[0]);
  }
  const n = selected.reduce((total, cell) => total + cell.n, 0);
  const hits = selected.reduce((total, cell) => total + cell.hits, 0);
  return { n, hits, pct: 100 * hits / n, leads: 7 };
}

export function matchingHistoricalCells(cells: HistoricalCell[], series: string, model: string | undefined, horizon: string, lead: number) {
  const contract = horizon === 'daily' ? 'daily7_current_local' : `${horizon}_complete_period_persistence`;
  return cells.filter(c => c.series === series && c.model_run_id === model && c.horizon === horizon && c.contract === contract && Number(c.lead) === lead && c.route !== 'unavailable');
}
