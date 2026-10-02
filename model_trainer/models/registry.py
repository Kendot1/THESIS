"""Thread-safe loader for one complete immutable model bundle."""
from threading import RLock

from features.builder import FeatureBuilder
from models.ensemble import EnsembleModel
from models.forecast_engine import ForecastEngine
from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.model_store import ModelStore


class ModelRegistry:
    _instance = None
    _instance_lock = RLock()

    def __init__(self):
        self._lock = RLock()
        self._loaded = False
        self.run_id = None
        self.engine = None

    @classmethod
    def get(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def load_all(self, force=False):
        with self._lock:
            if self._loaded and not force:
                return self
            store = ModelStore()
            path = store.active_path()
            builder = FeatureBuilder(path).load()
            lgbm = LightGBMModel(path)
            lgbm.load()
            lstm = LSTMModel(path)
            lstm.load()
            ensemble = EnsembleModel(path)
            ensemble.load()
            self.engine = ForecastEngine(lgbm, lstm, ensemble, builder)
            self.run_id = path.name
            self._loaded = True
            return self

    def reload(self):
        return self.load_all(force=True)

    @property
    def is_loaded(self):
        return self._loaded
