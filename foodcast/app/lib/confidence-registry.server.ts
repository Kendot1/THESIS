import 'server-only';
import { access, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import type { AdmittedConfidence, PicpAdmittedConfidence } from './forecast-evidence';

type RawPicpRecord = {
  model_run_id: string;
  commodity_id: string;
  series_key: string;
  category?: string;
  name?: string;
  variant?: string;
  origin?: string;
  unit?: string;
  forecast_horizon: 'daily' | 'weekly' | 'monthly';
  target_coverage: number;
  empirical_coverage: number | null;
  covered_count: number;
  sample_count: number;
  calibration_sample_count: number;
  calibration_origin_count: number;
  interval_half_width_php: number | null;
  calibration_period: string;
  evaluation_period: string;
  evaluation_timestamp: string;
  status: 'valid' | 'insufficient_data' | 'invalid_intervals';
};

type RawPicpArtifact = {
  schema_version: number;
  metric: string;
  model_run_id: string;
  metadata_sha256: string;
  validation_forecasts_sha256: string;
  test_forecasts_sha256: string;
  target_coverage: number;
  records: RawPicpRecord[];
};

async function resolveArtifactsRoot(): Promise<string> {
  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, 'artifacts', 'picp'),
    path.resolve(cwd, 'foodcast', 'artifacts', 'picp'),
    path.resolve(cwd, '..', 'model_trainer', 'artifacts_v2'),
    path.resolve(cwd, 'model_trainer', 'artifacts_v2'),
    path.resolve(cwd, '..', '..', 'model_trainer', 'artifacts_v2'),
  ];
  for (const candidate of candidates) {
    try {
      await access(path.join(candidate, 'manifest.json'));
      return candidate;
    } catch {
      // Next candidates vary between local development and deployed layouts.
    }
  }
  return candidates[0];
}

async function sha256File(filePath: string): Promise<string> {
  const bytes = await readFile(filePath);
  return createHash('sha256').update(bytes).digest('hex');
}

function toPicpEntry(record: RawPicpRecord, activeRunId: string): PicpAdmittedConfidence | null {
  const parts = String(record.series_key ?? '').split('||');
  const category = record.category ?? parts[0] ?? '';
  const name = record.name ?? parts[1] ?? '';
  const variant = record.variant ?? parts[2] ?? '';
  const origin = record.origin ?? parts[3] ?? '';
  const unit = record.unit ?? parts[4] ?? '';
  if (!category || !name || !variant || !origin || !unit) {
    return null;
  }
  return {
    method: 'out_of_sample_picp',
    verified: true,
    approved: record.status === 'valid' && record.model_run_id === activeRunId,
    evidenceId: `picp:${record.model_run_id}:${record.commodity_id}:${record.forecast_horizon}:${record.target_coverage}`,
    active_model_run_id: activeRunId,
    model_run_id: record.model_run_id,
    commodity_id: record.commodity_id,
    series_key: record.series_key,
    category,
    name,
    variant,
    origin,
    unit,
    route: 'model',
    forecast_horizon: record.forecast_horizon,
    target_coverage: Number(record.target_coverage),
    empirical_coverage:
      record.empirical_coverage == null ? null : Number(record.empirical_coverage),
    covered_count: Number(record.covered_count),
    sample_count: Number(record.sample_count),
    calibration_sample_count: Number(record.calibration_sample_count),
    calibration_origin_count: Number(record.calibration_origin_count),
    interval_half_width_php:
      record.interval_half_width_php == null ? null : Number(record.interval_half_width_php),
    calibration_period: String(record.calibration_period ?? ''),
    evaluation_period: String(record.evaluation_period ?? ''),
    evaluation_timestamp: String(record.evaluation_timestamp ?? ''),
    status: record.status,
  };
}

export async function loadActiveModelPicpArtifact(
  artifactsRoot: string | Promise<string> = resolveArtifactsRoot()
): Promise<{ activeRunId: string; artifact: RawPicpArtifact } | null> {
  try {
    artifactsRoot = await artifactsRoot;
    const manifestPath = path.join(artifactsRoot, 'manifest.json');
    const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
    const activeRunId = String(manifest?.active_run ?? '');
    if (!activeRunId) return null;

    const bundleDir = path.join(artifactsRoot, 'runs', activeRunId);
    const metadataPath = path.join(bundleDir, 'metadata.json');
    const metadataHash = await sha256File(metadataPath);
    const expectedMetaHash = manifest?.promotion_evidence?.model_metadata_sha256;
    if (expectedMetaHash && metadataHash !== expectedMetaHash) {
      return null;
    }

    const metadata = JSON.parse(await readFile(metadataPath, 'utf8'));
    if (metadata?.run_id !== activeRunId) return null;

    const evalPath = path.join(
      artifactsRoot,
      'confidence_evaluations',
      `${activeRunId}.json`
    );
    const artifact = JSON.parse(await readFile(evalPath, 'utf8')) as RawPicpArtifact;
    if (
      artifact?.schema_version !== 1 ||
      artifact?.metric !== 'PICP' ||
      artifact?.model_run_id !== activeRunId ||
      artifact?.metadata_sha256 !== metadataHash ||
      artifact?.validation_forecasts_sha256 !== metadata?.sha256?.['validation_forecasts.csv'] ||
      artifact?.test_forecasts_sha256 !== metadata?.sha256?.['test_forecasts.csv'] ||
      !Array.isArray(artifact?.records)
    ) {
      return null;
    }
    return { activeRunId, artifact };
  } catch {
    return null;
  }
}

export async function approvedConfidenceRegistry(
  _options?: { artifactsRoot?: string }
): Promise<AdmittedConfidence[]> {
  // Serving uses only the configured Supabase project. The offline artifact
  // loader remains available for audit tools, never as a serving fallback.
  try {
    const { supabase } = await import('../../lib/supabase');
    const { data, error } = await supabase.rpc('read_model_confidence_evaluations');
    if (error || !data?.model_run_id || !Array.isArray(data.records)) return [];
    const entries: AdmittedConfidence[] = [];
    for (const stored of data.records) {
      if (stored.independently_approved !== true || !stored.evaluation) continue;
      const entry = toPicpEntry(stored.evaluation as RawPicpRecord, data.model_run_id);
      if (entry && entry.status === 'valid' && entry.approved) entries.push(entry);
    }
    return entries;
  } catch {
    return [];
  }
}
