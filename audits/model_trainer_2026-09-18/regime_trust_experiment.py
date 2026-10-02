"""Chronologically cross-validated regime trust calibration experiment."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2] / "model_trainer" / "artifacts_v2" / "runs"
ALPHAS = np.linspace(0.0, 1.5, 31)


def enrich(frame):
    result = frame.copy()
    parts = result.series.astype(str).str.split("||", regex=False)
    result["category"] = parts.str[0]
    result["horizon_bin"] = np.digitize(result.horizon, [3, 7, 14, 21], right=True)
    relative_move = (result.ensemble-result.anchor) / result.anchor
    result["direction"] = np.sign(relative_move).astype(int)
    result["magnitude_bin"] = np.digitize(
        np.abs(relative_move), [.0025, .005, .01, .02, .05], right=True)
    return result


def metrics(rows, prediction):
    actual = rows.actual.to_numpy(float)
    error = np.asarray(prediction, dtype=float)-actual
    return np.array([
        np.mean(np.abs(error)),
        np.sqrt(np.mean(np.square(error))),
        100*np.mean(np.abs(error)/np.maximum(np.abs(actual), 1e-8)),
    ])


def prediction(rows, alpha):
    return rows.anchor.to_numpy(float) + alpha*(
        rows.ensemble.to_numpy(float)-rows.anchor.to_numpy(float))


def choose(rows):
    baseline = metrics(rows, rows.ensemble)
    candidates = []
    for alpha in ALPHAS:
        value = metrics(rows, prediction(rows, alpha))
        candidates.append((float(np.mean(value/baseline)), float(alpha)))
    return min(candidates)


def ratio(rows, alpha):
    return metrics(rows, prediction(rows, alpha))/metrics(rows, rows.ensemble)


def learn(validation, groups, minimum_rows=30, minimum_gain=.0025):
    origins = np.sort(pd.to_datetime(validation.origin).unique())
    cutoff = origins[len(origins)//2-1]
    early = validation[pd.to_datetime(validation.origin) <= cutoff]
    late = validation[pd.to_datetime(validation.origin) > cutoff]
    early_groups = early.groupby(groups, observed=True)
    late_groups = late.groupby(groups, observed=True)
    state = {}
    diagnostics = {}
    for key in sorted(set(early_groups.groups) & set(late_groups.groups)):
        left, right = early_groups.get_group(key), late_groups.get_group(key)
        if len(left) < minimum_rows or len(right) < minimum_rows:
            continue
        _, left_alpha = choose(left)
        _, right_alpha = choose(right)
        left_ratio = ratio(left, right_alpha)
        right_ratio = ratio(right, left_alpha)
        if not ((left_ratio < 1).all() and (right_ratio < 1).all()):
            continue
        if left_ratio.mean() > 1-minimum_gain or right_ratio.mean() > 1-minimum_gain:
            continue
        # Conservative value closest to no adjustment that succeeded cross-half.
        alpha = left_alpha if abs(left_alpha-1) <= abs(right_alpha-1) else right_alpha
        normalized = key if isinstance(key, tuple) else (key,)
        state[normalized] = alpha
        diagnostics["||".join(map(str, normalized))] = {
            "alpha": alpha,
            "early_selected": left_alpha,
            "late_selected": right_alpha,
            "early_ratio": left_ratio.tolist(),
            "late_ratio": right_ratio.tolist(),
        }
    return state, diagnostics, cutoff


def apply(frame, state, groups):
    result = frame.ensemble.to_numpy(float).copy()
    anchors = frame.anchor.to_numpy(float)
    for key, indices in frame.groupby(groups, observed=True).indices.items():
        normalized = key if isinstance(key, tuple) else (key,)
        alpha = state.get(normalized)
        if alpha is not None:
            result[indices] = anchors[indices] + alpha*(result[indices]-anchors[indices])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    run = ROOT / args.run_id
    validation = enrich(pd.read_csv(run / "validation_forecasts.csv"))
    test = enrich(pd.read_csv(run / "test_forecasts.csv"))
    candidates = [
        ["horizon_bin", "direction", "magnitude_bin"],
        ["category", "horizon_bin", "direction", "magnitude_bin"],
        ["category", "direction", "magnitude_bin"],
    ]
    results = []
    for groups in candidates:
        state, diagnostics, cutoff = learn(validation, groups)
        val_prediction = apply(validation, state, groups)
        test_prediction = apply(test, state, groups)
        results.append({
            "groups": groups,
            "cutoff": str(cutoff),
            "accepted_regimes": len(state),
            "validation_baseline": metrics(validation, validation.ensemble).tolist(),
            "validation_candidate": metrics(validation, val_prediction).tolist(),
            "test_baseline": metrics(test, test.ensemble).tolist(),
            "test_candidate": metrics(test, test_prediction).tolist(),
            "state": diagnostics,
        })
    output = Path(__file__).with_name(f"regime_trust_{args.run_id}.json")
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps([{k: v for k, v in row.items() if k != "state"}
                      for row in results], indent=2))


if __name__ == "__main__":
    main()
