import assert from "node:assert/strict"
import test from "node:test"
import { realizedForecastQuality } from "./quality.ts"
import { verifiedLongRangeHitRate, verifiedCoverageConfidenceInterval } from "../../../foodcast/app/lib/data.ts"

const product = {
  id: "rice-kg", name: "Rice", variant: "Regular", origin: "LOCAL",
  category: "Rice", unit: "kg",
}

function price(date, value, sourceDate = date) {
  const [year, month, day] = sourceDate.split("-")
  const monthName = new Date(`${year}-${month}-01T00:00:00Z`)
    .toLocaleString("en-US", { month: "long", timeZone: "UTC" })
  return {
    product_name: product.name, product_category: product.category,
    product_variant: product.variant, origin: product.origin, unit: product.unit,
    report_date: date, price_index: value,
    source_pdf: `Price-Monitoring-${monthName}-${Number(day)}-${year}.pdf`,
  }
}

function forecast(runId, date, lower, upper, point = (lower + upper) / 2) {
  return {
    run_id: runId, product_id: product.id, prediction_date: date,
    lower_bound: lower, upper_bound: upper, predicted_price: point,
  }
}

test("scores a product/date once using its latest pre-date forecast", () => {
  const runs = [
    { id: "early", generated_at: "2026-09-25T08:00:00Z" },
    { id: "late", generated_at: "2026-09-25T09:00:00Z" },
  ]
  const result = realizedForecastQuality(runs, [
    forecast("early", "2026-09-26", 90, 110),
    forecast("late", "2026-09-26", 110, 130),
    forecast("early", "2026-09-27", 90, 110),
    forecast("late", "2026-09-27", 90, 110),
  ], [product], [price("2026-09-26", 100), price("2026-09-27", 100)])

  assert.equal(result.sample_count, 2)
  assert.equal(result.product_metrics[product.id].sample_count, 2)
  assert.equal(result.product_metrics[product.id].interval_coverage, 0.5)
  assert.equal(result.product_metrics[product.id].interval_level, 0.8)
  assert.equal(result.interval_level, 0.8)
  assert.equal(result.product_metrics[product.id].sample_basis, "unique_actual_dates")
})

test("wide ranges do not inflate point prediction success", () => {
  const runs = [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }]
  const result = realizedForecastQuality(runs, [
    forecast("run", "2026-09-26", 1, 300, 150),
    forecast("run", "2026-09-27", 1, 300, 105),
  ], [product], [price("2026-09-26", 100), price("2026-09-27", 100)])
  assert.equal(result.interval_coverage, 1)
  assert.equal(result.prediction_success, 0.5)
  assert.equal(result.product_metrics[product.id].horizon_metrics.days_1_7.effective_sample_count, null)
  assert.equal(result.success_tolerance, 0.05)
  assert.equal(result.mae, 27.5)
  assert.ok(Math.abs(result.mape - 27.5) < 1e-10)
  assert.equal(result.rmse, Math.sqrt((2500 + 25) / 2))
})

test("uses the Philippine publication date and excludes same-local-day forecasts", () => {
  const runs = [{ id: "run", generated_at: "2026-09-25T17:00:00Z" }]
  const result = realizedForecastQuality(runs, [
    forecast("run", "2026-09-26", 90, 110),
  ], [product], [price("2026-09-26", 100)])
  assert.equal(result, null)
})

test("does not join observations across different product categories", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }],
    [forecast("run", "2026-09-26", 90, 110)], [product],
    [{ ...price("2026-09-26", 100), product_category: "Corn" }])
  assert.equal(result, null)
})

test("invalid point prices and inverted ranges do not contribute evidence", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }], [
      forecast("run", "2026-09-26", 90, 110, NaN),
      forecast("run", "2026-09-27", 110, 90),
    ], [product], [price("2026-09-26", 100), price("2026-09-27", 100)])
  assert.equal(result, null)
})

test("excludes same-day forecasts, copied prices, and conflicting actuals", () => {
  const runs = [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }]
  const result = realizedForecastQuality(runs, [
    forecast("run", "2026-09-25", 90, 110),
    forecast("run", "2026-09-26", 90, 110),
    forecast("run", "2026-09-27", 90, 110),
    forecast("run", "2026-09-28", 90, 110),
  ], [product], [
    price("2026-09-25", 100),
    price("2026-09-26", 100, "2026-09-25"),
    price("2026-09-27", 100),
    price("2026-09-27", 120),
    price("2026-09-28", 100),
  ])

  assert.equal(result.sample_count, 1)
  assert.equal(result.product_metrics[product.id].interval_coverage, 1)
})

test("retains long-lead misses when a newer next-day forecast hits", () => {
  const runs = [
    { id: "long", generated_at: "2026-09-01T08:00:00Z" },
    { id: "short", generated_at: "2026-09-25T08:00:00Z" },
  ]
  const result = realizedForecastQuality(runs, [
    forecast("long", "2026-09-26", 110, 130),
    forecast("short", "2026-09-26", 90, 110),
  ], [product], [price("2026-09-26", 100)])
  const byHorizon = result.product_metrics[product.id].horizon_metrics
  assert.equal(result.sample_count, 1)
  assert.equal(result.interval_coverage, 1)
  assert.equal(byHorizon.days_1_7.interval_coverage, 1)
  assert.equal(byHorizon.days_15_30.interval_coverage, 0)
  assert.equal(byHorizon.days_15_30.covered_count, 0)
  assert.equal(byHorizon.days_15_30.sample_count, 1)
  assert.equal(byHorizon.days_15_30.observed_min_lead_days, 25)
  assert.equal(byHorizon.days_15_30.mae, 20)
  assert.equal(byHorizon.days_15_30.rmse, 20)
  assert.equal(byHorizon.days_15_30.mape, 20)
})

test("deduplicates reruns within each lead-time bucket regardless of input order", () => {
  const runs = [
    { id: "early", generated_at: "2026-09-01T08:00:00Z" },
    { id: "late", generated_at: "2026-09-05T08:00:00Z" },
  ]
  const rows = [forecast("early", "2026-09-26", 90, 110),
                forecast("late", "2026-09-26", 110, 130)]
  for (const forecasts of [rows, rows.toReversed()]) {
    const result = realizedForecastQuality(runs, forecasts, [product], [price("2026-09-26", 100)])
    const long = result.product_metrics[product.id].horizon_metrics.days_15_30
    assert.equal(long.sample_count, 1)
    assert.equal(long.interval_coverage, 0)
    assert.equal(long.observed_min_lead_days, 21)
    assert.equal(long.observed_max_lead_days, 21)
  }
})

test("uses local-day bucket boundaries and excludes leads over thirty days", () => {
  // 17:00 UTC is already September 2 in the Philippines.
  const runs = [{ id: "run", generated_at: "2026-09-01T17:00:00Z" }]
  const dates = ["2026-09-03", "2026-09-09", "2026-09-10", "2026-09-16",
                 "2026-09-17", "2026-10-02", "2026-10-03"]
  const result = realizedForecastQuality(runs, dates.map((d) => forecast("run", d, 90, 110)),
                                        [product], dates.map((d) => price(d, 100)))
  const buckets = result.product_metrics[product.id].horizon_metrics
  assert.equal(buckets.days_1_7.sample_count, 2)
  assert.equal(buckets.days_8_14.sample_count, 2)
  assert.equal(buckets.days_15_30.sample_count, 2)
  assert.equal(buckets.days_15_30.observed_min_lead_days, 15)
  assert.equal(buckets.days_15_30.observed_max_lead_days, 30)
  assert.equal(result.sample_count, 7)
  assert.equal(result.covered_count, 7)
})

test("does not fabricate long-range evidence from short forecasts", () => {
  const result = realizedForecastQuality([{ id: "run", generated_at: "2026-09-25T08:00:00Z" }],
    [forecast("run", "2026-09-26", 90, 110)], [product], [price("2026-09-26", 100)])
  assert.equal(result.product_metrics[product.id].horizon_metrics.days_15_30, undefined)
})

test("serial dependence reduces the coverage confidence effective sample size", () => {
  const dates = Array.from({ length: 14 }, (_, index) => {
    const date = new Date(Date.UTC(2026, 8, 26 + index)).toISOString().slice(0, 10)
    return date
  })
  const runs = [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }]
  const forecasts = dates.map((date, index) => index < 3 || index >= 7
    ? forecast("run", date, 90, 110)
    : forecast("run", date, 110, 130))
  const result = realizedForecastQuality(runs, forecasts, [product], dates.map((date) => price(date, 100)))
  const shortLead = result.product_metrics[product.id].horizon_metrics.days_1_7
  assert.equal(shortLead.sample_count, 7)
  assert.ok(shortLead.effective_sample_count >= 1)
  assert.ok(shortLead.effective_sample_count < shortLead.sample_count)
  assert.equal(shortLead.coverage_uncertainty_method, "positive_serial_wilson_7d")
  assert.equal(shortLead.coverage_uncertainty_approximate, true)
  assert.equal(shortLead.coverage_uncertainty_validated, false)
})

test("conflicting forecasts within one run are excluded independent of order", () => {
  const runs = [{ id: "run", generated_at: "2026-09-01T08:00:00Z" }]
  const rows = [forecast("run", "2026-09-26", 90, 110),
                forecast("run", "2026-09-26", 110, 130),
                forecast("run", "2026-09-27", 90, 110)]
  for (const forecasts of [rows, rows.toReversed()]) {
    const result = realizedForecastQuality(runs, forecasts, [product],
      [price("2026-09-26", 100), price("2026-09-27", 100)])
    assert.equal(result.sample_count, 1)
    assert.equal(result.interval_coverage, 1)
    assert.equal(result.product_metrics[product.id].horizon_metrics.days_15_30.sample_count, 1)
  }
})

test("identical duplicate forecasts count once", () => {
  const row = forecast("run", "2026-09-26", 90, 110)
  const result = realizedForecastQuality([{ id: "run", generated_at: "2026-09-01T08:00:00Z" }],
    [row, { ...row }], [product], [price("2026-09-26", 100)])
  assert.equal(result.sample_count, 1)
})

test("conflicting publication timestamps cannot move a run into a preferred bucket", () => {
  const runs = [{ id: "run", generated_at: "2026-09-01T08:00:00Z" },
                { id: "run", generated_at: "2026-09-25T08:00:00Z" }]
  for (const ordered of [runs, runs.toReversed()]) {
    assert.equal(realizedForecastQuality(ordered, [forecast("run", "2026-09-26", 90, 110)],
      [product], [price("2026-09-26", 100)]), null)
  }
})

test("invalid calendar dates do not silently roll into another month", () => {
  const result = realizedForecastQuality([{ id: "run", generated_at: "2026-02-01T08:00:00Z" }],
    [forecast("run", "2026-02-30", 90, 110)], [product], [price("2026-02-30", 100)])
  assert.equal(result, null)
})

test("real backend history displays a measured hit rate but withholds uncalibrated confidence", () => {
  const dates = Array.from({ length: 30 }, (_, i) => new Date(Date.UTC(2024, 0, 20 + i)).toISOString().slice(0, 10))
  const runs = dates.map((date, i) => ({ id: `r${i}`, generated_at: new Date(Date.parse(date) - 20 * 86400000).toISOString() }))
  const forecasts = dates.map((date, i) => forecast(`r${i}`, date, i < 24 ? 90 : 110, i < 24 ? 110 : 130))
  const result = realizedForecastQuality(runs, forecasts, [product], dates.map(date => price(date, 100)))
  const metrics = result.product_metrics[product.id].horizon_metrics.days_15_30
  assert.equal(verifiedLongRangeHitRate(metrics), .8)
  assert.ok(metrics.effective_sample_count > 0)
  assert.equal(verifiedCoverageConfidenceInterval(metrics), null)
})
