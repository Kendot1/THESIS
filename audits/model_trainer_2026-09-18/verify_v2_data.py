"""Offline data-contract verification for the repaired v2 trainer."""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))

from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.builder import FEATURE_COLUMNS, FeatureBuilder, usable_targets
from models.lstm_model import LSTMModel


raw = pd.DataFrame(json.loads((Path(__file__).parent / "food_prices_snapshot.json").read_text(
    encoding="utf-8")))
clean = DataPreprocessor().validate(raw)
train, validation, test = DataPreprocessor.split_three(clean)
with tempfile.TemporaryDirectory() as temporary:
    builder = FeatureBuilder(Path(temporary)).fit(train)
    featured = builder.transform(clean)
    model = LSTMModel(Path(temporary)).fit_scalers(train)
    sequences = {}
    for name, part in [("train", train), ("validation", validation), ("test", test)]:
        mask = featured.report_date.between(part.report_date.min(), part.report_date.max())
        x, y, _, keys, _ = model.build_sequences(
            featured, part.report_date.min(), part.report_date.max())
        sequences[name] = {
            "lightgbm_observed_rows": int((mask & usable_targets(featured)).sum()),
            "lstm_sequences": int(len(x)),
            "lstm_observed_targets": int(np.isfinite(y).sum()),
            "lstm_series": int(len(set(keys))),
        }

result = {
    "raw_rows": len(raw), "daily_panel_rows": len(clean),
    "observed_rows": int(clean.is_observed.sum()),
    "series": int(clean.groupby(SERIES_KEY).ngroups),
    "date_min": str(clean.report_date.min().date()),
    "date_max": str(clean.report_date.max().date()),
    "features": len(FEATURE_COLUMNS),
    "partitions": {
        name: {"start": str(part.report_date.min().date()),
               "end": str(part.report_date.max().date()), "rows": len(part)}
        for name, part in [("train", train), ("validation", validation), ("test", test)]
    },
    "usable": sequences,
}
print(json.dumps(result, indent=2))
