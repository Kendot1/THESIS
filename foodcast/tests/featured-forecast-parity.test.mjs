import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('featured price uses the same daily-derived selector as ForecastChart', () => {
  const source = fs.readFileSync(new URL('../app/client/Predict.tsx', import.meta.url), 'utf8');
  assert.match(source, /marketAnalysisForecasts\(\{\s*forecastData: featuredChartData,\s*forecastOriginDate: featuredChartOrigin,\s*forecastSource: "model",?\s*\}, featuredHorizon\)\[0\]/);
});
