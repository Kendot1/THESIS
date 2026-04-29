"""
Pydantic schemas for API request / response models.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import date


# ──────────────────────────────────────────────
# Prediction
# ──────────────────────────────────────────────
class PredictionRequest(BaseModel):
    product_name: str = Field(
        ..., description="Name of the product to forecast",
        json_schema_extra={"examples": ["Tomato"]},
    )
    product_variant: Optional[str] = Field(
        None, description="Product variant, e.g., 'Lakatan', 'Cherry'",
        json_schema_extra={"examples": ["Standard"]},
    )
    origin: Optional[str] = Field(
        None, description="Product origin: 'Local' or 'Imported'",
        json_schema_extra={"examples": ["Local"]},
    )
    product_category: Optional[str] = Field(
        None, description="Product category, e.g., 'Vegetables', 'Fruits'",
        json_schema_extra={"examples": ["Vegetables"]},
    )
    horizon: str = Field(
        default="daily",
        description="Forecast horizon: 'daily', 'weekly', or 'monthly'",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "product_name": "Tomato",
                    "product_variant": "Standard",
                    "origin": "Local",
                    "product_category": "Vegetables",
                    "horizon": "weekly",
                },
                {
                    "product_name": "Garlic",
                    "horizon": "daily",
                },
            ]
        }
    }


class PredictionPoint(BaseModel):
    date: str
    predicted_price: float
    lower_bound: float
    upper_bound: float
    confidence_level: float = Field(default=0.8, description="Confidence interval level (80%)")


class PredictionResponse(BaseModel):
    product_name: str
    product_variant: Optional[str] = None
    origin: Optional[str] = None
    product_category: Optional[str] = None
    horizon: str
    current_price: Optional[float] = None
    predictions: List[PredictionPoint]
    model_version: Optional[str] = None


# ──────────────────────────────────────────────
# Explanation
# ──────────────────────────────────────────────
class ExplanationRequest(BaseModel):
    product_name: str = Field(
        ..., json_schema_extra={"examples": ["Banana"]},
    )
    product_variant: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Lakatan"]},
    )
    origin: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Local"]},
    )
    product_category: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Fruits"]},
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "product_name": "Banana",
                    "product_variant": "Lakatan",
                    "origin": "Local",
                    "product_category": "Fruits",
                },
            ]
        }
    }


class FeatureContribution(BaseModel):
    feature: str
    importance: float
    description: str


class NewsEvidence(BaseModel):
    event: str
    impact: str
    confidence: float
    reason: str


class ReasoningData(BaseModel):
    trend: str
    data_factors: List[str]
    news_factors: List[str]
    confidence_explanation: str
    risk_factors: List[str]

class ExplanationResponse(BaseModel):
    product_name: Optional[str] = None
    product_variant: Optional[str] = None
    origin: Optional[str] = None
    product_category: Optional[str] = None
    reasoning: ReasoningData


# ──────────────────────────────────────────────
# Comparison
# ──────────────────────────────────────────────
class ComparisonRequest(BaseModel):
    product_name: str = Field(
        ..., json_schema_extra={"examples": ["Onion"]},
    )
    product_variant: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Red"]},
    )
    origin: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Imported"]},
    )
    product_category: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Vegetables"]},
    )
    compare_by: str = Field(
        default="history",
        description="'history' | 'origin' | 'variant'",
    )
    period_days: int = Field(default=30, ge=1, le=365)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "product_name": "Onion",
                    "product_variant": "Red",
                    "compare_by": "origin",
                    "period_days": 30,
                },
            ]
        }
    }


class PricePoint(BaseModel):
    date: str
    price: float
    label: Optional[str] = None


class ComparisonResponse(BaseModel):
    product_name: str
    product_variant: Optional[str] = None
    origin: Optional[str] = None
    product_category: Optional[str] = None
    compare_by: str
    current_price: float
    series: Dict[str, List[PricePoint]]  # label → points


# ──────────────────────────────────────────────
# Recommendation
# ──────────────────────────────────────────────
class RecommendationRequest(BaseModel):
    product_name: str = Field(
        ..., json_schema_extra={"examples": ["Beef"]},
    )
    product_variant: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Rump"]},
    )
    origin: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Local"]},
    )
    product_category: Optional[str] = Field(
        None, json_schema_extra={"examples": ["Meat"]},
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "product_name": "Beef",
                    "product_variant": "Rump",
                    "origin": "Local",
                    "product_category": "Meat",
                },
            ]
        }
    }


class Alternative(BaseModel):
    product_name: str
    product_variant: Optional[str] = None
    origin: Optional[str] = None
    product_category: str
    current_price: float
    price_difference: float
    price_difference_pct: float
    reason: str


class RecommendationResponse(BaseModel):
    original_product: str
    original_variant: Optional[str] = None
    original_origin: Optional[str] = None
    original_category: Optional[str] = None
    original_price: float
    predicted_direction: str
    alternatives: List[Alternative]
    recommendation_reason: str = ""


# ──────────────────────────────────────────────
# Training
# ──────────────────────────────────────────────
class TrainRequest(BaseModel):
    mode: str = Field(
        default="incremental",
        description="'full' or 'incremental'",
    )


class TrainResponse(BaseModel):
    status: str
    mode: str
    metrics: Dict
    version: Optional[str] = None


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    latest_version: Optional[str] = None
    latest_data_date: Optional[str] = None
