# FOODCAST — AI Food Price Forecasting Model Trainer

A production-grade hybrid **LightGBM + LSTM** food price forecasting system with continuous learning, explainability, and real-time news integration.

## Architecture

```
┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
│  Supabase DB │──▶│ Data Fetcher │──▶│ Feature Engineer │
│ (food_prices)│   │ (paginated)  │   │ (temporal, lag,  │
└──────────────┘   └──────────────┘   │  rolling, cat.)  │
                                       └────────┬─────────┘
                                                │
                          ┌─────────────────────┼─────────────────────┐
                          ▼                     ▼                     ▼
                   ┌─────────────┐      ┌──────────────┐     ┌──────────────┐
                   │  LightGBM   │      │    LSTM      │     │    News      │
                   │  (tabular)  │      │ (sequences)  │     │  Sentiment   │
                   └──────┬──────┘      └──────┬───────┘     └──────────────┘
                          │                    │
                          ▼                    ▼
                   ┌───────────────────────────────┐
                   │     Ensemble (Stacking)       │
                   │   Ridge Meta-Learner          │
                   └──────────────┬────────────────┘
                                  │
                                  ▼
                   ┌───────────────────────────────┐
                   │       FastAPI Server          │
                   │  /predictions                 │
                   │  /explanations                │
                   │  /comparisons                 │
                   │  /recommendations             │
                   └───────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
cd d:\THESIS\model_trainer
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env` file:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
```

### 3. Train the Models

```bash
# Full training from scratch
python main.py train --mode full

# Incremental update (daily)
python main.py train --mode incremental

# Smart daily run (checks drift, decides mode)
python main.py train --mode daily
```

### 4. Start the API

```bash
python main.py serve
# Or with hot reload for development:
python main.py serve --reload
```

### 5. Schedule Daily Training

```bash
python main.py schedule --time 02:00
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/predictions/` | Get price forecasts (daily/weekly/monthly) |
| `GET`  | `/predictions/products` | List available products |
| `POST` | `/explanations/` | Get prediction reasoning |
| `POST` | `/comparisons/` | Compare prices (history/origin/variant) |
| `POST` | `/recommendations/` | Get cheaper alternatives |
| `POST` | `/train` | Trigger training |
| `GET`  | `/health` | Health check |
| `GET`  | `/versions` | List model versions |
| `GET`  | `/docs` | Swagger UI |

## Features

- **Hybrid Model**: LightGBM for tabular features + LSTM for temporal patterns
- **50+ Engineered Features**: Lag, rolling, volatility, cyclical, seasonal, sentiment
- **Confidence Intervals**: Quantile regression (LightGBM) + MC Dropout (LSTM)
- **Incremental Training**: Warm-start models on new data without full retrain
- **Drift Detection**: PSI-based distribution monitoring with auto-retrain triggers
- **Model Versioning**: Rolling checkpoint history with rollback support
- **Explainability**: Feature importance + news evidence + human-readable summaries
- **Recommendations**: Suggests cheaper alternatives when prices rise

## Evaluation Metrics

- **RMSE** — Root Mean Squared Error
- **MAE** — Mean Absolute Error
- **MAPE** — Mean Absolute Percentage Error

Tracked per: product, category, and forecast horizon.
