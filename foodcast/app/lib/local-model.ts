import type { ForecastDataPoint } from './data';
import type { StagingForecast } from '../research-model-test/staging';

export function selectLocalResearch(enabled: boolean, search: string, mode = 'calendar-research'): boolean {
  const selected = new URLSearchParams(search).get('model');
  return enabled && (mode === 'rolling-research' ? selected === 'rolling-research' : selected !== 'incumbent');
}

// Do not mix current incumbent actuals, predictions, intervals or confidence
// with the historical saved research origin.
export function researchChartPoints(rows: StagingForecast[]): ForecastDataPoint[] {
  return rows.map(row => ({
    date: row.target_end,
    name: `${row.target_start} to ${row.target_end}`,
    actual: null,
    predicted: row.unavailable || row.prediction == null || !Number.isFinite(row.prediction) ? null : row.prediction,
    horizon: row.horizon,
    target_period_start: row.target_start,
    target_period_end: row.target_end,
    forecast_step: row.lead,
    confidence_score: null,
    confidence_level: 'Insufficient data',
  }));
}
