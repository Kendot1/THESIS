import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const runtime = 'nodejs';

interface SavedPredictionRow {
  series: string;
  target_start: string;
  actual: number;
  incumbent_served: number;
}

let cachedCsvData: SavedPredictionRow[] | null = null;

function loadSavedPredictions(): SavedPredictionRow[] {
  if (cachedCsvData) return cachedCsvData;
  try {
    const filePath = path.join(process.cwd(), 'artifacts/accuracy/saved_predictions.csv');
    if (!fs.existsSync(filePath)) return [];

    const fileContent = fs.readFileSync(filePath, 'utf-8');
    const lines = fileContent.split('\n');
    const header = lines[0].split(',').map((h) => h.trim());
    const seriesIdx = header.indexOf('series');
    const dateIdx = header.indexOf('target_start');
    const actualIdx = header.indexOf('actual');
    const predIdx = header.indexOf('incumbent_served');

    if (seriesIdx === -1 || dateIdx === -1 || actualIdx === -1 || predIdx === -1) {
      return [];
    }

    const rows: SavedPredictionRow[] = [];
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      const cols = line.split(',');
      const series = cols[seriesIdx]?.trim();
      const date = cols[dateIdx]?.trim();
      const actual = parseFloat(cols[actualIdx]);
      const pred = parseFloat(cols[predIdx]);

      if (series && date && !isNaN(actual) && !isNaN(pred) && actual > 0) {
        rows.push({
          series,
          target_start: date,
          actual,
          incumbent_served: pred,
        });
      }
    }

    cachedCsvData = rows;
    return rows;
  } catch (err) {
    console.error('Failed to load saved_predictions.csv:', err);
    return [];
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const name = searchParams.get('name')?.trim().toLowerCase();
  const variant = searchParams.get('variant')?.trim().toLowerCase();

  if (!name) {
    return NextResponse.json({ error: 'name parameter is required' }, { status: 400 });
  }

  const allRows = loadSavedPredictions();
  const matched = allRows.filter((r) => {
    const s = r.series.toLowerCase();
    const matchesName = s.includes(name);
    if (!matchesName) return false;
    if (variant && variant !== 'standard' && !variant.includes('standard')) {
      return s.includes(variant);
    }
    return true;
  });

  const pointsByDate = new Map<string, { date: string; actual: number; predicted: number }>();
  for (const r of matched) {
    pointsByDate.set(r.target_start, {
      date: r.target_start,
      actual: r.actual,
      predicted: r.incumbent_served,
    });
  }

  const sortedPoints = [...pointsByDate.values()].sort((a, b) => a.date.localeCompare(b.date));

  return NextResponse.json({
    product: name,
    variant: variant || 'Standard',
    points: sortedPoints,
  });
}
