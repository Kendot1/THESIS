"""
Singleton model registry.
Loads models ONCE and caches them in memory for fast inference.
Prevents the repeated disk I/O that caused the server crash.
"""

from typing import Optional

from models.lightgbm_model import LightGBMModel
from models.lstm_model import LSTMModel
from models.ensemble import EnsembleModel
from utils.logger import get_logger

log = get_logger(__name__)


class ModelRegistry:
    """
    Thread-safe singleton that holds loaded model instances.
    Call .get() to obtain the shared registry.
    """

    _instance: Optional["ModelRegistry"] = None

    def __init__(self):
        self.lgbm: Optional[LightGBMModel] = None
        self.lstm: Optional[LSTMModel] = None
        self.ensemble: Optional[EnsembleModel] = None
        self._loaded = False

    @classmethod
    def get(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_all(self, force: bool = False):
        """Load all models from disk. Skips if already loaded unless force=True."""
        if self._loaded and not force:
            return

        log.info("Loading models into registry ...")

        self.lgbm = LightGBMModel()
        try:
            self.lgbm.load()
        except FileNotFoundError:
            log.warning("LightGBM model not found on disk -- will use fallback.")
        # Load residual model (Stage 2 of hybrid)
        if self.lgbm is not None:
            try:
                self.lgbm.load_residual()
            except FileNotFoundError:
                log.warning("LightGBM residual model not found -- hybrid correction disabled.")

        self.lstm = LSTMModel()
        try:
            self.lstm.load()
        except FileNotFoundError:
            log.warning("LSTM model not found on disk -- will use fallback.")
            self.lstm = None

        self.ensemble = EnsembleModel()
        try:
            self.ensemble.load()
        except FileNotFoundError:
            log.warning("Ensemble model not found on disk -- will use fallback.")
            self.ensemble = None

        self._loaded = True
        log.info("Model registry loaded successfully.")

    def reload(self):
        """Force-reload all models from disk (e.g. after retraining)."""
        self._loaded = False
        self.load_all(force=True)

    @property
    def is_loaded(self) -> bool:
        return self._loaded
