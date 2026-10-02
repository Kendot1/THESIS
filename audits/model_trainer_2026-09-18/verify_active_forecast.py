"""Load the active v2 registry and exercise its live forecast path offline."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model_trainer"))

from data.preprocessor import DataPreprocessor, SERIES_KEY
from models.registry import ModelRegistry

raw = pd.DataFrame(json.loads((Path(__file__).parent / "food_prices_snapshot.json").read_text(
    encoding="utf-8")))
clean = DataPreprocessor().validate(raw)
registry = ModelRegistry.get().load_all()
errors = []
for key, group in clean.groupby(SERIES_KEY, sort=True):
    try:
        forecast = registry.engine.forecast(group, horizon=7)
        print(json.dumps({
            "run_id": registry.run_id,
            "series": list(key),
            "anchor": forecast.anchor,
            "dates": [str(pd.Timestamp(value).date()) for value in forecast.dates],
            "point": forecast.point.tolist(),
            "lower": forecast.lower.tolist(),
            "upper": forecast.upper.tolist(),
        }, indent=2))
        break
    except ValueError as exc:
        errors.append({"series": list(key), "error": str(exc)})
else:
    raise RuntimeError(f"No series could be forecast; first errors: {errors[:3]}")
