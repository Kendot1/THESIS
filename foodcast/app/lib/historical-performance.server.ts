import "server-only";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import manifest from "./historical-accuracy.json";

export function parseCsv(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = []; let field = ""; let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i++; } else quoted = !quoted;
    } else if (c === ',' && !quoted) { row.push(field); field = ""; }
    else if (c === '\n' && !quoted) { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
    else field += c;
  }
  if (quoted) throw new Error("Unclosed CSV field");
  if (field || row.length) { row.push(field.replace(/\r$/, "")); rows.push(row); }
  return rows;
}

export function accuracyFromRows(rows: string[][]): number | null {
  const [header, ...data] = rows;
  const index = (name: string) => { const n = header.indexOf(name); if (n < 0) throw new Error("Missing column"); return n; };
  const a = index("actual"), p = index("incumbent_served");
  const h = index("horizon_name"), lead = index("lead");
  const keyFields = ["horizon_name", "series", "forecast_origin", "target_start", "target_end", "lead"].map(index);
  const dates = ["forecast_origin", "target_start", "target_end"].map(index);
  const keys = new Set<string>(); let total = 0; let count = 0;
  for (const row of data) {
    if (row.length !== header.length || row[h] !== "daily_7d" || +row[lead] < 1 || +row[lead] > 7) throw new Error("Wrong contract");
    if (dates.some(i => !/^\d{4}-\d{2}-\d{2}$/.test(row[i]) || row[i] >= "2026-10-06")) throw new Error("Ineligible date");
    const key = JSON.stringify(keyFields.map(i => row[i]));
    if (keys.has(key)) throw new Error("Duplicate key"); keys.add(key);
    if (!row[a].trim() || !row[p].trim()) continue;
    const actual = Number(row[a]), predicted = Number(row[p]);
    if (!Number.isFinite(actual) || !Number.isFinite(predicted) || actual < 1e-8 || predicted < 0) continue;
    total += Math.abs(actual - predicted) / Math.abs(actual); count++;
  }
  return count ? 100 - 100 * total / count : null;
}

/** Daily-7 historical reference, not a claim about the currently served checkpoint. */
export async function homepagePerformance() {
  try {
    const entry = Object.entries(manifest.input_hashes).find(([name]) => name.replaceAll('\\', '/').endsWith('/daily7/saved_predictions.csv'));
    if (!entry) throw new Error("No daily source");
    const filename = path.resolve(process.cwd(), "..", entry[0].replaceAll('\\', '/'));
    const bytes = await readFile(filename);
    if (createHash("sha256").update(bytes).digest("hex") !== entry[1]) throw new Error("Hash mismatch");
    const rows = parseCsv(bytes.toString("utf8"));
    if (rows.length - 1 !== manifest.evaluated_predictions) throw new Error("Required grid mismatch");
    return { historical_forecast_accuracy_pct: accuracyFromRows(rows) };
  } catch {
    return { historical_forecast_accuracy_pct: null };
  }
}
