"""Metrics on aligned, observed price targets."""
import numpy as np

SUCCESS_TOLERANCE = .05


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
    a, p = _aligned(y_true, y_pred)
    result = {'mae': compute_mae(a,p), 'rmse': compute_rmse(a,p),
              'mape': compute_mape(a,p), 'r2': compute_r2(a,p), 'n': len(a),
              'prediction_success': float(np.mean(abs(a-p)/abs(a) <= SUCCESS_TOLERANCE)),
              'success_tolerance': SUCCESS_TOLERANCE}
    if anchors is not None:
        result['directional_accuracy'] = compute_directional_accuracy(a,p,anchors)
    return result
