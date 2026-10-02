interface PriceRow {
  product_name: string;
  product_variant: string | null;
  origin: string | null;
  product_category: string | null;
  price_index: number;
  unit: string | null;
}

export interface DashboardSummaryRow {
  first_row: PriceRow;
  last_row: PriceRow;
  meta: { id: string; category: string | null; image_url: string | null } | null;
  recent_prices: number[];
  prediction_prices: number[];
}

export function normalizeSeriesUnit(row: any): string {
  const category = String(row.product_category ?? row.category ?? "");
  const name = String(row.product_name ?? row.name ?? "");
  const variant = String(row.product_variant ?? row.variant ?? "").toLowerCase();
  if (category === "Oils" && variant === "1l") return "liter";
  if (category === "Oils" && variant === "350ml") return "350ml";
  if (name === "Chicken Egg") return "piece";
  const unit = String(row.unit ?? "unknown").trim().toLowerCase() || "unknown";
  const aliases: Record<string, string> = {
    "per kg": "kg", kilogram: "kg", pc: "piece", "per piece": "piece",
    l: "liter", "1 liter": "liter", "1l": "liter", "350 ml": "350ml",
    milliliter: "ml", btl: "bottle",
  };
  return aliases[unit] ?? unit;
}

export function productSeriesKey(row: any): string {
  return [row.product_name ?? row.name ?? "",
          row.product_variant ?? row.variant ?? "",
          row.origin ?? "", normalizeSeriesUnit(row)].join("|");
}

// Reuse the legacy JS helpers and arithmetic: SQL numeric rounding/AVG changes
// results for floating-point and nullable prices returned by the original API.
export function mapDashboardSummary(rows: DashboardSummaryRow[], helpers: {
  slugify: (value: string) => string;
  defaultImage: string;
}) {
  const mapped = rows.map(({ first_row: first, last_row: last, meta, prediction_prices }) => {
    const name = first.product_name;
    const variant = first.product_variant || "";
    const origin = first.origin || "";
    const currentPrice = last.price_index;
    const predictedPrice = prediction_prices.length > 0
      ? Math.round((prediction_prices.reduce((sum, price) => sum + price, 0) / prediction_prices.length) * 100) / 100
      : currentPrice;
    return {
      id: meta ? meta.id : helpers.slugify(`${name} ${variant} ${origin}`),
      name, category: meta?.category || first.product_category || "Other",
      image: meta?.image_url || helpers.defaultImage, variant, origin,
      currentPrice, predictedPrice, unit: normalizeSeriesUnit(last),
      forecastSource: prediction_prices.length > 0 ? "model" : "trend_fallback",
    };
  });
  return mapped.sort((a, b) => a.name.localeCompare(b.name));
}
