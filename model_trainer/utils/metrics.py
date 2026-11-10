"""Metrics on aligned, observed price targets."""
import numpy as np

SUCCESS_TOLERANCE = .05
WITHIN_5_PHP_TOLERANCE = 5.0


def _aligned(y_true, y_pred):
    a, p = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if a.ndim != 1 or p.shape != a.shape or not len(a):
        raise ValueError('Metrics require nonempty aligned one-dimensional arrays')
    if not np.isfinite(a).all() or not np.isfinite(p).all():
        raise ValueError('Nonfinite metric inputs')
    return a, p


def compute_rmse(y_true, y_pred):
    a, p = _aligned(y_true, y_pred)
    return float(np.sqrt(np.mean((a-p)**2)))


def compute_mae(y_true, y_pred):
    a, p = _aligned(y_true, y_pred)
    return float(np.mean(abs(a-p)))


def compute_mape(y_true, y_pred):
    a, p = _aligned(y_true, y_pred)
    if np.any(abs(a) < 1e-8):
        raise ValueError('MAPE undefined for zero/near-zero targets')
    return float(np.mean(abs((a-p)/a))*100)


def compute_forecast_accuracy(y_true, y_pred):
    """Mean of (1 - abs(actual - forecast) / actual) * 100.

    Requires observed positive actuals >= 1e-8, matching MAPE's numerical
    threshold. This retrospective percentage is not forecast confidence.
    Negative results are retained when relative error exceeds 100%.
    Use compute_all_metrics for exclusion counts and unavailable results.
    """
    a, p = _aligned(y_true, y_pred)
    if np.any(a < 1e-8):
        raise ValueError('Forecast accuracy requires positive targets >= 1e-8')
    return float(100 - compute_mape(a, p))


def compute_r2(y_true, y_pred):
    a, p = _aligned(y_true, y_pred)
    variance = np.sum((a-a.mean())**2)
    return float(1-np.sum((a-p)**2)/variance) if variance else None


def compute_directional_accuracy(y_true, y_pred, anchors):
    a, p = _aligned(y_true, y_pred)
    _, origin = _aligned(a, anchors)
    # Flat moves count as a distinct class, never automatically as correct.
    return float(np.mean(np.sign(a-origin) == np.sign(p-origin))*100)


def compute_all_metrics(y_true, y_pred, anchors=None):
    a, p = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if a.ndim != 1 or p.shape != a.shape or not len(a):
        raise ValueError('Metrics require nonempty aligned one-dimensional arrays')
    directional_rows = None
    anchor_values = None
    if anchors is not None:
        anchor_values = np.asarray(anchors, dtype=float)
        if anchor_values.ndim != 1 or anchor_values.shape != a.shape:
            raise ValueError('Directional anchors must align with actual/prediction rows')
    # A food price cannot be negative. Keep zero actuals for absolute error
    # metrics, but exclude them from percentage metrics where division is
    # undefined. Nonfinite pairs and negative actuals are excluded together.
    valid = np.isfinite(a) & np.isfinite(p) & (a >= 0)
    if anchor_values is not None:
        directional_rows = valid & np.isfinite(anchor_values)
    excluded_invalid = int(len(a) - np.count_nonzero(valid))
    a, p = a[valid], p[valid]
    if not len(a):
        result = {
            'mae': None, 'rmse': None, 'mape': None, 'r2': None, 'n': 0,
            'invalid_sample_count': excluded_invalid,
            'forecast_accuracy_pct': None,
            'forecast_accuracy_sample_count': 0,
            'forecast_accuracy_excluded_zero_or_near_zero': 0,
            'within_5_php_count': 0,
            'within_5_php_tolerance': WITHIN_5_PHP_TOLERANCE,
            'within_5_php_sample_count': 0,
            'within_5_php_accuracy_pct': None,
            'within_5_percent_count': 0,
            'within_5_percent_accuracy_pct': None,
            'within_5_percent_sample_count': 0,
            'within_5_percent_excluded_zero_or_near_zero': 0,
            'prediction_success': None,
            'success_tolerance': SUCCESS_TOLERANCE,
            'within_10_count': 0,
            'within_10_accuracy_pct': None,
            'within_10_sample_count': 0,
            'within_10_excluded_near_zero': 0,
        }
        if anchor_values is not None:
            result['directional_accuracy'] = None
            result['directional_sample_count'] = 0
        return result

    absolute_errors = np.abs(a - p)
    percentage_rows = np.abs(a) >= 1e-8
    percentage_errors = (absolute_errors[percentage_rows]
                         / np.abs(a[percentage_rows]))
    within_5_count = int(np.count_nonzero(absolute_errors <= WITHIN_5_PHP_TOLERANCE))
    within_5_percent_count = int(np.count_nonzero(percentage_errors <= SUCCESS_TOLERANCE))
    within_10_count = int(np.count_nonzero(percentage_errors <= .10))
    mape = float(np.mean(percentage_errors) * 100) if len(percentage_errors) else None
    within_5_percent_accuracy = (
        within_5_percent_count * 100 / len(percentage_errors)
        if len(percentage_errors) else None)
    result = {'mae': compute_mae(a,p), 'rmse': compute_rmse(a,p),
              'mape': mape, 'r2': compute_r2(a,p), 'n': len(a),
              'invalid_sample_count': excluded_invalid,
              # Mean row-level percentage closeness; not a probability or hit rate.
              'forecast_accuracy_pct': 100 - mape if mape is not None else None,
              'forecast_accuracy_sample_count': int(len(percentage_errors)),
              'forecast_accuracy_excluded_zero_or_near_zero': int(
                  len(a) - len(percentage_errors)),
              'within_5_php_count': within_5_count,
              'within_5_php_tolerance': WITHIN_5_PHP_TOLERANCE,
              'within_5_php_sample_count': int(len(a)),
              'within_5_php_accuracy_pct': within_5_count * 100 / len(a),
              'within_5_percent_count': within_5_percent_count,
              'within_5_percent_accuracy_pct': within_5_percent_accuracy,
              'within_5_percent_sample_count': int(len(percentage_errors)),
              'within_5_percent_excluded_zero_or_near_zero': int(
                  len(a) - len(percentage_errors)),
              # Preserve the serving field's established 0..1 meaning.
              'prediction_success': (within_5_percent_accuracy / 100
                                     if within_5_percent_accuracy is not None else None),
              'success_tolerance': SUCCESS_TOLERANCE,
              'within_10_count': within_10_count,
              'within_10_accuracy_pct': (
                  within_10_count * 100 / len(percentage_errors)
                  if len(percentage_errors) else None),
              'within_10_sample_count': int(len(percentage_errors)),
              'within_10_excluded_near_zero': int(len(a) - len(percentage_errors))}
    if anchor_values is not None:
        directional_rows = directional_rows[valid]
        result['directional_accuracy'] = (
            compute_directional_accuracy(
                a[directional_rows], p[directional_rows],
                anchor_values[valid][directional_rows])
            if np.any(directional_rows) else None)
        result['directional_sample_count'] = int(np.count_nonzero(directional_rows))
    return result
