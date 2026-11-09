import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from '../../../foodcast/tests/load-ts.mjs';
const {resolveForecastOrigin,selectFuturePredictions}=loadTs('../../supabase/functions/foodcast/forecast.ts');
test('new observations do not move the origin of an existing saved model vintage',()=>{
 assert.equal(resolveForecastOrigin('2026-11-10','2026-11-09'),'2026-11-09');
 const rows=[{prediction_date:'2026-11-10',predicted_price:66,forecast_origin_date:'2026-11-09'},{prediction_date:'2026-11-11',predicted_price:67,forecast_origin_date:'2026-11-09'}];
 assert.equal(selectFuturePredictions(rows,resolveForecastOrigin('2026-11-10','2026-11-09')).length,2);
});
