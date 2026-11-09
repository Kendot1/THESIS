import "server-only";
import { readFile } from "node:fs/promises";

export type StagingForecast = {
  horizon: "daily" | "weekly" | "monthly";
  forecast_origin: string;
  lead: number;
  target_start: string;
  target_end: string;
  series: string;
  product_series: {
    product_category: string;
    product_name: string;
    product_variant: string;
    origin: string;
    unit: string;
  };
  prediction: number | null;
  model: string;
  fallback: boolean;
  fallback_reason: string | null;
  unavailable: boolean;
  history_date: string | null;
  confidence_score: number | null;
  confidence_level: string;
  confidence_reason: string;
};

// Fixed allowlist: never derive filesystem paths from request input or env values.
const files = [
  "D:/THESIS/audits/staging_calendar_inference_20261106/daily7.json",
  "D:/THESIS/audits/staging_calendar_inference_20261106/weekly4.json",
  "D:/THESIS/audits/staging_calendar_inference_20261106/monthly1.json",
] as const;

export async function readStagingForecasts(): Promise<StagingForecast[]> {
  if (process.env.NODE_ENV !== "development") {
    throw new Error("Staging forecasts are development-only");
  }
  const batches = await Promise.all(files.map(async (file) => {
    const rows: StagingForecast[] = JSON.parse(await readFile(file, "utf8"));
    if (!Array.isArray(rows) || rows.some(row => row.forecast_origin !== "2026-01-01")) {
      throw new Error("Unexpected staging forecast origin or format");
    }
    return rows;
  }));
  return batches.flat();
}
