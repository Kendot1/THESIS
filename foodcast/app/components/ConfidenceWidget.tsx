import { unavailableEvidence, type ForecastEvidence } from '../lib/forecast-evidence';

export function getConfidenceColor(value: number | null, loading = false): string {
  if (loading || value == null || !Number.isFinite(value)) return '#64748b';
  if (value >= 80) return '#2E7D32';
  if (value >= 60) return '#ff8134';
  return '#C62828';
}

export function ConfidenceRing({
  value,
  color,
  label,
  whole = false,
  loading = false,
}: {
  value: number | null;
  color: string;
  label: string;
  whole?: boolean;
  loading?: boolean;
}) {
  const available = !loading && value != null && Number.isFinite(value);
  const fill = available ? Math.max(0, Math.min(100, value)) : 0;
  const text = loading ? '…' : available ? `${whole ? Math.round(value) : value.toFixed(1)}%` : '—';
  return (
    <div
      className="relative h-[50px] w-[50px] shrink-0 rounded-full"
      role={available ? 'meter' : 'img'}
      aria-label={label}
      aria-valuemin={available ? Math.min(0, value) : undefined}
      aria-valuemax={available ? 100 : undefined}
      aria-valuenow={available ? value : undefined}
      aria-valuetext={loading ? 'Loading confidence...' : available ? text : 'Confidence unavailable · Insufficient data'}
    >
      <svg viewBox="0 0 50 50" width="50" height="50" aria-hidden="true" className="block">
        <circle cx="25" cy="25" r="23" fill="none" stroke="#e5e7eb" strokeWidth="4" />
        <circle
          data-ring-value={fill}
          cx="25"
          cy="25"
          r="23"
          fill="none"
          stroke={fill > 0 ? color : 'none'}
          strokeWidth="4"
          strokeLinecap="round"
          pathLength="100"
          strokeDasharray={`${fill} 100`}
          transform="rotate(-90 25 25)"
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center font-extrabold tabular-nums"
        style={{ color: available ? color : '#6b7280', fontSize: text.length > 5 ? 9 : text.length > 4 ? 10 : 12 }}
      >
        {text}
      </span>
    </div>
  );
}

/** Never infers confidence classifications from a percentage or accepts raw legacy scores. */
export default function ConfidenceWidget({
  evidence,
  details,
  loading = false,
  modelRunId,
}: {
  evidence?: ForecastEvidence;
  value?: number | null;
  details?: string;
  loading?: boolean;
  modelRunId?: string;
  evaluationDate?: string;
}) {
  const approved =
    !loading &&
    evidence?.kind === 'approvedconfidence' &&
    Number.isFinite(evidence.value) &&
    evidence.value >= 0 &&
    evidence.value <= 100 &&
    !!evidence.evidenceId &&
    !!evidence.details;
  const resolved =
    approved || evidence?.kind === 'unavailable'
      ? evidence!
      : unavailableEvidence(
          details ??
            (evidence?.kind === 'historicalaccuracy'
              ? 'Historical accuracy is retrospective, not approved confidence.'
              : undefined)
        );
  const value = loading ? null : resolved.value;
  const available = !loading && value != null && Number.isFinite(value);
  const evaluation = resolved.kind === 'approvedconfidence' ? resolved.evaluation : undefined;
  const color = getConfidenceColor(value, loading);
  const text = loading
    ? 'Loading confidence...'
    : available
      ? `${value.toFixed(1)}%`
      : 'Confidence unavailable · Insufficient data';
  const label = 'Confidence level';
  const resolvedRunId = evaluation?.model_run_id || modelRunId || '';

  return (
    <div
      data-testid="forecast-confidence"
      data-confidence-state={loading ? 'loading' : available ? 'available' : 'unavailable'}
      data-evidence-kind={loading ? 'loading' : resolved.kind}
      data-evidence-id={!loading && 'evidenceId' in resolved ? resolved.evidenceId : undefined}
      data-model-run-id={resolvedRunId || undefined}
      aria-busy={loading ? 'true' : undefined}
      aria-label={`${label}: ${text}`}
      className="flex w-full min-w-0 items-center gap-3 text-gray-900"
      style={{ maxWidth: 260 }}
    >
      <ConfidenceRing value={value} color={color} label={label} loading={loading} />
      <span className="min-w-0 text-xs font-bold leading-relaxed" style={{ overflowWrap: 'anywhere' }}>
        {label}
        {loading && (
          <span className="block text-gray-500" data-testid="confidence-loading">
            Loading confidence...
          </span>
        )}
        {!loading && !available && (
          <span className="block text-gray-500" data-testid="confidence-unavailable">
            Confidence unavailable · Insufficient data
          </span>
        )}
      </span>
    </div>
  );
}
