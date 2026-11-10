"""Read-only support accounting; does not change model eligibility or predictions."""
import numpy as np
import pandas as pd


def analyze_support(rows, base_identities):
    """Return every required row with a reason and frozen-fallback error floor.

    Known identity gaps are not asserted to be short history: they may reflect
    missing, stale or invalid sequences. Unseen identities are not automatically
    eligible for a trained global model. No fallback is replaced here.
    """
    result = rows.copy()
    fallback = result.fallback.astype(bool)
    known = result.series.isin(base_identities)
    result['support_reason'] = np.where(
        ~fallback, 'hybrid_supported',
        np.where(~known, 'unseen_base_identity', 'known_identity_sequence_unavailable'))
    actual = pd.to_numeric(result.actual, errors='coerce').to_numpy(float)
    persistence = pd.to_numeric(result.persistence, errors='coerce').to_numpy(float)
    prediction = pd.to_numeric(result.candidate_prediction, errors='coerce').to_numpy(float)
    valid_label = np.isfinite(actual) & (actual >= 0)
    scored = valid_label & np.isfinite(prediction)
    fallback_scored = fallback.to_numpy() & scored
    if not np.isfinite(persistence[fallback_scored]).all():
        raise ValueError('Nonfinite fallback reference')
    result['fallback_squared_error'] = np.where(
        fallback_scored, np.square(persistence - actual), 0.)
    sse = float(result.fallback_squared_error.sum())
    denominator = int(scored.sum())
    floor = float(np.sqrt(sse / denominator)) if denominator else None
    return result, dict(required=len(result), scored=denominator,
                        missing_labels=int(np.isnan(actual).sum()),
                        invalid_labels=int((~np.isnan(actual) & (~np.isfinite(actual) | (actual < 0))).sum()),
                        missing_predictions=int(np.isnan(prediction).sum()),
                        invalid_predictions=int((~np.isnan(prediction) & ~np.isfinite(prediction)).sum()),
                        fallback_required=int(fallback.sum()),
                        fallback_scored=int(fallback_scored.sum()), fallback_sse=sse,
                        fallback_rmse_floor=floor,
                        rmse_goal_feasible_with_frozen_fallback=(floor < 5 if floor is not None else None))
