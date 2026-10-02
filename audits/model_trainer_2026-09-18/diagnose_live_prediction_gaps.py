"""Read-only diagnosis of active live point-forecast gaps."""
import json
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2] / "model_trainer"
sys.path.insert(0, str(ROOT))

from data.fetcher import DataFetcher
from data.preprocessor import DataPreprocessor, SERIES_KEY
from models.registry import ModelRegistry
from pipeline.prediction_writer import PredictionWriter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data")
    args = parser.parse_args()
    if args.data:
        payload = json.loads(Path(args.data).read_text(encoding="utf-8"))
        raw = pd.DataFrame(payload.get("rows", payload) if isinstance(payload, dict) else payload)
    else:
        raw = DataFetcher().fetch_all()
    clean = DataPreprocessor().validate(raw)
    registry = ModelRegistry.get().load_all()
    results = []
    for key, series in clean.groupby(SERIES_KEY, sort=True):
        source = "ensemble"
        try:
            forecast = registry.engine.forecast(series, 30)
            point = forecast.point
        except ValueError as exc:
            if not PredictionWriter._is_history_shortfall(exc):
                continue
            _, point, _, _ = PredictionWriter._persistence_fallback(
                registry.engine, series, 30)
            source = "persistence_fallback"
        anchor = float(series.sort_values("report_date").price_index.iloc[-1])
        first_gap = 100*(float(point[0])-anchor)/anchor
        last_gap = 100*(float(point[-1])-anchor)/anchor
        max_gap = 100*np.max(np.abs(np.asarray(point)-anchor))/anchor
        results.append({
            "series": dict(zip(SERIES_KEY, key)), "source": source,
            "anchor": anchor, "day_1": float(point[0]), "day_30": float(point[-1]),
            "day_1_gap_percent": first_gap, "day_30_gap_percent": last_gap,
            "max_absolute_gap_percent": float(max_gap),
        })
    results.sort(key=lambda row: row["max_absolute_gap_percent"], reverse=True)
    print(json.dumps({"model_run_id": registry.run_id, "series": len(results),
                      "largest_point_gaps": results[:20]}, indent=2))


if __name__ == "__main__":
    main()
