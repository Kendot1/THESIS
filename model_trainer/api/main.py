"""
FastAPI application -- FOODCAST Model Trainer API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import predictions, explanations, comparisons, recommendations
from api.schemas import HealthResponse, TrainRequest, TrainResponse
from models.model_store import ModelStore
from data.fetcher import DataFetcher
from utils.logger import get_logger

log = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FOODCAST -- AI Price Forecasting API",
        description=(
            "Hybrid LightGBM + LSTM food price forecasting system. "
            "Provides predictions, explanations, comparisons, and recommendations."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS (allow foodcast frontend)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register route modules
    app.include_router(predictions.router)
    app.include_router(explanations.router)
    app.include_router(comparisons.router)
    app.include_router(recommendations.router)

    # ── Health endpoint ──
    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health():
        store = ModelStore()
        versions = store.list_versions()
        latest = versions[-1] if versions else None

        try:
            fetcher = DataFetcher()
            latest_date = fetcher.fetch_latest_date()
        except Exception:
            latest_date = None

        return HealthResponse(
            status="healthy",
            model_loaded=latest is not None,
            latest_version=latest["version"] if latest else None,
            latest_data_date=latest_date,
        )

    # ── Training trigger endpoint ──
    @app.post("/train", response_model=TrainResponse, tags=["Training"])
    async def trigger_training(request: TrainRequest):
        from pipeline.trainer import TrainingPipeline

        pipeline = TrainingPipeline()
        if request.mode == "full":
            metrics = pipeline.run_full_training()
        else:
            metrics = pipeline.run_incremental_training()

        store = ModelStore()
        versions = store.list_versions()
        latest_version = versions[-1]["version"] if versions else None

        return TrainResponse(
            status="completed",
            mode=request.mode,
            metrics=metrics,
            version=latest_version,
        )

    # ── Model versions endpoint ──
    @app.get("/versions", tags=["System"])
    async def list_versions():
        store = ModelStore()
        return {"versions": store.list_versions()}

    @app.on_event("startup")
    async def startup():
        log.info("FOODCAST API starting up ...")

    return app


# For running with `uvicorn api.main:app`
app = create_app()
