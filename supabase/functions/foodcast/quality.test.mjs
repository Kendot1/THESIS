import assert from "node:assert/strict"
import test from "node:test"
import { realizedForecastQuality } from "./quality.ts"

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

function forecast(runId, origin, date, point, horizon = "daily", step = 1) {
  return {
    run_id: runId, product_id: product.id, forecast_origin_date: origin,
    prediction_date: date, predicted_price: point,
    forecast_horizon: horizon, forecast_step: step,
  }
}

test("scores each product/date once using its latest saved point forecast", () => {
  const runs = [
    { id: "early", generated_at: "2026-09-25T08:00:00Z" },
    { id: "late", generated_at: "2026-09-25T09:00:00Z" },
  ]
  const result = realizedForecastQuality(runs, [
    forecast("early", "2026-09-25", "2026-09-26", 90),
    forecast("late", "2026-09-25", "2026-09-26", 110),
    forecast("early", "2026-09-25", "2026-09-27", 90),
    forecast("late", "2026-09-25", "2026-09-27", 100),
  ], [product], [price("2026-09-26", 100), price("2026-09-27", 100)])

  assert.equal(result.sample_count, 2)
  assert.equal(result.product_metrics[product.id].sample_count, 2)
  assert.equal(result.mae, 5)
  assert.equal(result.prediction_success, 0.5)
  assert.equal(result.product_metrics[product.id].horizon_metrics.days_1_7.sample_count, 2)
  assert.equal("interval_coverage" in result, false)
})

test("only persisted daily rows are matched to individual observed dates", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }], [
      forecast("run", "2026-09-25", "2026-09-26", 100, "daily", 1),
      forecast("run", "2026-09-25", "2026-09-27", 100, "weekly", 1),
    ], [product], [price("2026-09-26", 100), price("2026-09-27", 100)])
  assert.equal(result.sample_count, 1)
  assert.equal(result.product_metrics[product.id].sample_count, 1)
})

test("uses the saved origin date and excludes same-day forecasts", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T17:00:00Z" }],
    [forecast("run", "2026-09-26", "2026-09-26", 100)],
    [product], [price("2026-09-26", 100)])
  assert.equal(result, null)
})

test("does not join observations across different product categories", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }],
    [forecast("run", "2026-09-25", "2026-09-26", 100)], [product],
    [{ ...price("2026-09-26", 100), product_category: "Corn" }])
  assert.equal(result, null)
})

test("invalid point prices and invalid dates do not contribute evidence", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }], [
      forecast("run", "2026-09-25", "2026-09-26", NaN),
      forecast("run", "2026-09-25", "2026-02-30", 100),
    ], [product], [price("2026-09-26", 100)])
  assert.equal(result, null)
})

test("copied prices, zero or near-zero actuals, and conflicting observations are excluded", () => {
  const result = realizedForecastQuality(
    [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }], [
      forecast("run", "2026-09-25", "2026-09-26", 100),
      forecast("run", "2026-09-25", "2026-09-27", 100),
      forecast("run", "2026-09-25", "2026-09-28", 100),
    ], [product], [
      price("2026-09-26", 100, "2026-09-25"),
      price("2026-09-27", 0.000000001),
      price("2026-09-28", 100), price("2026-09-28", 120),
    ])
  assert.equal(result, null)
})

test("keeps lead-time buckets separate and excludes leads beyond day thirty", () => {
  const origin = "2026-09-01"
  const dates = ["2026-09-02", "2026-09-08", "2026-09-09", "2026-09-15",
    "2026-09-16", "2026-10-01", "2026-10-02"]
  const result = realizedForecastQuality([{ id: "run", generated_at: "2026-09-01T08:00:00Z" }],
    dates.map((date, index) => forecast("run", origin, date, index < 6 ? 100 : 999)),
    [product], dates.map(date => price(date, 100)))
  const buckets = result.product_metrics[product.id].horizon_metrics
  assert.equal(buckets.days_1_7.sample_count, 2)
  assert.equal(buckets.days_8_14.sample_count, 2)
  assert.equal(buckets.days_15_30.sample_count, 2)
  assert.equal(buckets.days_15_30.horizon_min_days, 15)
  assert.equal(buckets.days_15_30.horizon_max_days, 30)
  assert.equal(result.sample_count, 6)
})

test("ambiguous duplicate forecasts and conflicting run timestamps do not score", () => {
  const row = forecast("run", "2026-09-25", "2026-09-26", 100)
  const runs = [{ id: "run", generated_at: "2026-09-25T08:00:00Z" }]
  assert.equal(realizedForecastQuality(runs, [row, { ...row, predicted_price: 101 }],
    [product], [price("2026-09-26", 100)]), null)
  assert.equal(realizedForecastQuality([...runs,
    { id: "run", generated_at: "2026-09-24T08:00:00Z" }], [row],
  [product], [price("2026-09-26", 100)]), null)
})
