"""Reproducible local retrain and comparison; never publishes to Supabase/R2."""
import json
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model_trainer'))

from data.fetcher import DataFetcher
from pipeline.trainer import TrainingPipeline


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw = DataFetcher().fetch_all()
    raw.to_json(output / 'training_snapshot.json', orient='records', date_format='iso')
    metrics = TrainingPipeline().run_full_training(raw, activate=True)
    (output / 'training_result.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print(json.dumps({'run_id': metrics['run_id'], 'activated': metrics['activated'],
                      'test': metrics['test']['ensemble'],
                      'gate': metrics['promotion_gate']}, indent=2))
