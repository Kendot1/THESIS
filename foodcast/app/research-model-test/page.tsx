import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { readStagingForecasts, type StagingForecast } from "./staging";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const metadata: Metadata = {
  title: "Local staging forecasts | FOODCAST",
  robots: { index: false, follow: false },
};

export default async function ResearchModelTestPage({ searchParams }: {
  searchParams: Promise<{ series?: string | string[] }>;
}) {
  if (process.env.NODE_ENV !== "development") notFound();

  let rows: StagingForecast[];
  try {
    rows = await readStagingForecasts();
  } catch {
    return <main id="main-content" className="mx-auto max-w-6xl px-6 pt-32 pb-16">
      <h1 className="text-3xl font-bold">Local staging forecasts unavailable</h1>
      <p className="mt-4">The approved local staging files could not be read. No live forecasts or backend fallback were requested.</p>
    </main>;
  }
  const products = [...new Map(rows.map(row => [row.series, row.product_series])).entries()]
    .sort(([a], [b]) => a.localeCompare(b));
  const requested = (await searchParams).series;
  const selected = typeof requested === "string" && products.some(([key]) => key === requested)
    ? requested : products[0]?.[0];
  const selectedRows = rows.filter(row => row.series === selected);
  const identity = products.find(([key]) => key === selected)?.[1];

  return <main id="main-content" className="mx-auto max-w-6xl px-4 pt-32 pb-16 sm:px-6">
    <aside className="border-l-4 border-orange-dark bg-orange-light/20 p-5" aria-label="Research limitation">
      <h1 className="text-2xl font-bold text-primary-900">Retrospective staging forecasts — NOT live</h1>
      <p className="mt-2">Local development only. Forecast origin: January 1, 2026 (2026-01-01). Saved Calendar hybrid outputs, not current market forecasts.</p>
      <p className="mt-2">DA publication timing and revision history are unverified. Research diagnostics only; no deployment, activation or accuracy/calibration claim.</p>
    </aside>
    <section className="mt-8" aria-labelledby="model-heading">
      <h2 id="model-heading" className="text-xl font-semibold">Calendar hybrid</h2>
      <p className="mt-2">Recent Calendar LSTM + relative-residual LightGBM</p>
      <p className="mt-1 break-words text-sm">Model identity: recent_calendar_lstm_plus_relative_residual_lightgbm</p>
      <p className="mt-2 text-sm">Fallback rows use last_pre_origin_observed_persistence, not the hybrid model. Confidence is unavailable (null), not 0% or a guarantee.</p>
    </section>
    <form action="/research-model-test" method="get" className="my-8 flex flex-wrap items-end gap-3">
      <div className="min-w-0 flex-1">
        <label htmlFor="series" className="mb-2 block font-semibold">Product (category / name / variant / origin / unit)</label>
        <select id="series" name="series" defaultValue={selected} className="min-h-12 w-full rounded-lg border border-primary-800 bg-white px-3 text-base">
          {products.map(([key, product]) => <option key={key} value={key}>
            {[product.product_category, product.product_name, product.product_variant || "(no variant)", product.origin || "(no origin)", product.unit].join(" / ")}
          </option>)}
        </select>
      </div>
      <button type="submit" className="min-h-12 rounded-lg bg-primary-800 px-6 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2">View forecasts</button>
    </form>
    {identity && <p className="mb-6 break-words text-sm">Selected full identity: {selected}. Prices in PHP per {identity.unit}.</p>}
    {([ ["daily", "Daily · next 7 calendar days"], ["weekly", "Weekly · next 4 complete Monday–Sunday weeks"], ["monthly", "Monthly · next complete calendar month"] ] as const).map(([horizon, title]) => {
      const forecasts = selectedRows.filter(row => row.horizon === horizon).sort((a, b) => a.lead - b.lead);
      return <section key={horizon} className="mb-10" aria-labelledby={`${horizon}-heading`}>
        <h2 id={`${horizon}-heading`} className="mb-3 text-xl font-semibold text-primary-800">{title}</h2>
        {forecasts.length === 0 ? <p>No saved output available for this product and horizon.</p> :
          <div className="overflow-x-auto rounded-lg border border-primary-100">
            <table className="w-full min-w-[760px] border-collapse text-left text-sm">
              <caption className="sr-only">{title} saved forecasts, origin January 1, 2026</caption>
              <thead className="bg-primary-50"><tr>
                {["Step", "Target dates", "Price (PHP)", "Model / fallback", "Confidence"].map(label => <th key={label} scope="col" className="p-3 font-semibold">{label}</th>)}
              </tr></thead>
              <tbody>{forecasts.map(row => <tr key={row.lead} className="border-t border-primary-100 align-top">
                <td className="p-3">{row.lead}</td>
                <td className="p-3 whitespace-nowrap">{row.target_start}{row.target_end !== row.target_start && <> to<br />{row.target_end}</>}</td>
                <td className="p-3 whitespace-nowrap font-semibold tabular-nums">{row.unavailable || row.prediction === null ? "Unavailable" : `₱${row.prediction.toFixed(2)}`}</td>
                <td className="max-w-80 p-3 break-words">
                  <strong>{row.unavailable ? "Unavailable" : row.fallback ? "Fallback (persistence)" : "Model (Calendar hybrid)"}</strong>
                  <p className="mt-1 break-all">{row.model}</p>
                  {row.fallback_reason && <p className="mt-1">Reason: {row.fallback_reason}</p>}
                  <p className="mt-1">Last observation: {row.history_date ?? "Unavailable"}</p>
                </td>
                <td className="max-w-72 p-3">
                  <strong>{row.confidence_score === null ? "Unavailable (null)" : `${row.confidence_score}%`}</strong>
                  <p>{row.confidence_level}</p><p className="mt-1">{row.confidence_reason}</p>
                </td>
              </tr>)}</tbody>
            </table>
          </div>}
      </section>;
    })}
  </main>;
}
