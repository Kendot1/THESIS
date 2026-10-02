"""Compare saved candidates on identical observations, including interval score."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model_trainer'))
from models.ensemble import EnsembleModel
from pipeline.trainer import TrainingPipeline
from utils.metrics import compute_all_metrics


def evaluate(run_id):
    path = ROOT / 'model_trainer' / 'artifacts_v2' / 'runs' / run_id
    frame = pd.read_csv(path / 'test_forecasts.csv')
    model = EnsembleModel(path)
    model.load()
    intervals = TrainingPipeline._interval_metrics(model, frame)
    for level, report in intervals.items():
        report['weighted_category_calibration_error'] = sum(
            abs(row['observed_coverage']-float(level))*row['sample_count']
            for row in report['by_category'].values())/len(frame)
    return {'run_id': run_id,
            'point': compute_all_metrics(frame.actual, frame.ensemble, frame.anchor),
            'intervals': intervals, 'calibration': model.calibration}


if __name__ == '__main__':
    report = [evaluate(run_id) for run_id in sys.argv[1:]]
    destination = Path(__file__).with_name('candidate_comparison.json')
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for row in report:
        print(json.dumps({'run_id': row['run_id'], 'point': row['point'],
                          'intervals': {level: {k: v for k, v in value.items() if k != 'by_category'}
                                        for level, value in row['intervals'].items()}}, indent=2))
