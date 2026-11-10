import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';

let cachedCells: Record<string, unknown>[] | null = null;
let cachePromise: Promise<Record<string, unknown>[]> | null = null;

async function loadAndVerifyCells(): Promise<Record<string, unknown>[]> {
  const root = path.resolve(process.cwd(), '..');
  const reportBytes = await readFile(path.join(root, 'audits/product_accuracy_v1/historical_indicator_v1/SUPPORT.json'));
  if (createHash('sha256').update(reportBytes).digest('hex') !== '3eb152b0ec349703258fc4cc0d6f6e80beecb3e715a6f5458f1857401c7710e9') throw new Error('Summary changed');
  const report = JSON.parse(reportBytes.toString('utf8'));
  for (const [name, hash] of Object.entries(report.input_hashes)) {
    const bytes = await readFile(path.join(root, name));
    if (createHash('sha256').update(bytes).digest('hex') !== hash) throw new Error('Evidence changed');
  }
  return report.cells.map((cell: Record<string, unknown>) => ({ ...cell,
    product_identity: String(cell.series).split('||'),
    historical_confidence_pct: cell.pct,
    successful_forecast_count: cell.hits,
    eligible_forecast_count: cell.n,
    data_availability_status: cell.availability,
    evidence_provenance: 'serving_replay_v3:verified-origin-receipts',
    remote_serving_parity: 'UNVERIFIED',
  }));
}

export async function GET() {
  try {
    if (!cachedCells) {
      cachePromise ??= loadAndVerifyCells().then(cells => {
        cachedCells = cells;
        return cells;
      }).catch(err => {
        cachePromise = null;
        throw err;
      });
      await cachePromise;
    }
    return Response.json({ cells: cachedCells ?? [] }, {
      headers: { 'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=3600' }
    });
  } catch {
    return Response.json({ cells: [] }, { headers: { 'Cache-Control': 'no-store' } });
  }
}
