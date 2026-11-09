import assert from "node:assert/strict";
import test from "node:test";
import { mergePricePage } from "./price-series.ts";

const row = (report_date, price_index, unit = "kg") => ({
  product_name: "Tomato", product_category: "Vegetables", product_variant: null,
  origin: null, price_index, report_date, unit,
});

test("retains bounded chart and previous-price points while preserving full count", () => {
  const summaries = new Map();
  for (let day = 1; day <= 15; day++) mergePricePage(summaries, row(`2026-01-${String(day).padStart(2, "0")}`, day));
  const summary = summaries.get("Tomato|||kg");
  for (let day = 16; day <= 20; day++) mergePricePage(summaries, row(`2026-01-${day}`, day));
  assert.equal(summary.count, 20);
  assert.equal(summary.first.price_index, 1);
  assert.equal(summary.last.price_index, 20);
  assert.equal(summary.previous.price_index, 19);
  assert.equal(summary.recent.length, 8);
  assert.deepEqual(summary.recent.map(x => x.price_index), [13,14,15,16,17,18,19,20]);
});

test("preserves stable latest-row ordering for equal dates and normalized units", () => {
  const summaries = new Map();
  summarizePricePage(summaries, row("2026-01-01", 1, "KG"));
  summarizePricePage(summaries, row("2026-01-01", 2, "kg"));
  const summary = summaries.get("Tomato|||kg");
  assert.equal(summary.count, 2);
  assert.equal(summary.first.price_index, 1);
  assert.equal(summary.last.price_index, 2);
});
