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
