import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { readFile } from "node:fs/promises";
import path from "node:path";
import AccuracyPreview from "./AccuracyPreview";
import type { ProductAccuracy } from "../lib/product-accuracy";
import { verifiedHistoricalEvidence } from '../lib/forecast-evidence.server';

export const dynamic = "force-dynamic";

export default async function Page() {
  const hostname = (await headers()).get("host")?.split(":")[0];
  if (process.env.NODE_ENV !== "development" || !["localhost", "127.0.0.1"].includes(hostname ?? "")) notFound();
  const filename = path.resolve(process.cwd(), "../audits/product_accuracy_v1/results/PRODUCT_ACCURACY_API.json");
  const data: { products: ProductAccuracy[]; product_leads: ProductAccuracy[] } = JSON.parse(await readFile(filename, "utf8"));
  return <AccuracyPreview products={data.products} leads={data.product_leads} history={await verifiedHistoricalEvidence()} />;
}
