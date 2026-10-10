"""
Visualization utilities for FOODCAST training dashboards.
Generates clean, white-background static charts for thesis-quality output.

Plots generated:
  1. LSTM Training vs Validation Loss Curve
  2. Learning Rate Schedule
  3. Feature Importance (Top 15)
  4. Actual vs Predicted (Time Series)
  5. Residual Distribution
  6. Per-Category RMSE/MAE/MAPE Bar Chart
  7. Model Comparison Bar Chart (LSTM vs LightGBM vs Hybrid)
  8. Scatter Plot (Predicted vs Actual with y=x line)
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from typing import Dict, List, Union, Optional

# ──────────────────────────────────────────────
# Global Matplotlib style — clean white theme
# ──────────────────────────────────────────────
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"]
plt.rcParams["figure.facecolor"] = "#ffffff"
plt.rcParams["axes.facecolor"] = "#ffffff"
plt.rcParams["axes.edgecolor"] = "#cbd5e1"
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.color"] = "#e2e8f0"
plt.rcParams["grid.linestyle"] = "--"
plt.rcParams["grid.alpha"] = 0.6
plt.rcParams["text.color"] = "#1e293b"
plt.rcParams["axes.labelcolor"] = "#334155"
plt.rcParams["xtick.color"] = "#475569"
plt.rcParams["ytick.color"] = "#475569"
plt.rcParams["legend.facecolor"] = "#ffffff"
plt.rcParams["legend.edgecolor"] = "#cbd5e1"

# Consistent color palette
COLORS = {
    "primary": "#2563eb",     # Blue
    "secondary": "#7c3aed",   # Purple
    "success": "#059669",     # Green
    "danger": "#dc2626",      # Red
    "warning": "#d97706",     # Amber
    "info": "#0891b2",        # Cyan
    "lstm": "#2563eb",        # Blue
    "lgbm": "#7c3aed",        # Purple
    "hybrid": "#059669",      # Green
    "actual": "#1e293b",      # Dark slate
}


# ──────────────────────────────────────────────
# Plot 1: LSTM Training vs Validation Loss
# ──────────────────────────────────────────────
def plot_lstm_loss(history_path: Union[str, Path], save_path: Union[str, Path]):
    """
    Line plot for LSTM training and validation loss decay.
    Highlights the best early stopping epoch.
    """
    history_path = Path(history_path)
    save_path = Path(save_path)

    if not history_path.exists():
        raise FileNotFoundError(f"History file not found at {history_path}")

    with open(history_path, "r") as f:
        history = json.load(f)

    epochs = history.get("epoch", [])
    train_loss = history.get("train_loss", [])
    val_loss = history.get("val_loss", [])

    if not epochs or not train_loss:
        raise ValueError("Training history lacks epoch or train_loss statistics.")

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    ax.plot(epochs, train_loss, label="Training Loss", color=COLORS["primary"],
            linewidth=2.0, marker="o", markersize=3, markevery=max(1, len(epochs)//15))

    val_active = val_loss and any(v is not None for v in val_loss)
    if val_active:
        clean_val = [v if v is not None else np.nan for v in val_loss]
        ax.plot(epochs, clean_val, label="Validation Loss", color=COLORS["danger"],
                linewidth=2.0, marker="s", markersize=3, markevery=max(1, len(epochs)//15))

        # Highlight best epoch
        valid_indices = [i for i, v in enumerate(clean_val) if not np.isnan(v)]
        if valid_indices:
            best_idx = valid_indices[np.argmin([clean_val[i] for i in valid_indices])]
            best_epoch = epochs[best_idx]
            best_val = clean_val[best_idx]
            ax.scatter(best_epoch, best_val, color=COLORS["danger"], s=100, zorder=5,
                       edgecolors="#1e293b", linewidth=1.5,
                       label=f"Best Epoch ({best_epoch}: {best_val:.5f})")
            ax.axvline(x=best_epoch, color=COLORS["danger"], linestyle=":", alpha=0.4)

    ax.set_title("LSTM Training vs Validation Loss", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Epoch", fontsize=11, labelpad=10)
    ax.set_ylabel("Loss (MAE)", fontsize=11, labelpad=10)
    ax.legend(loc="upper right", framealpha=0.95)
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 2: Learning Rate Schedule
# ──────────────────────────────────────────────
def plot_learning_rate(history_path: Union[str, Path], save_path: Union[str, Path]):
    """
    Line plot of the learning rate schedule across epochs.
    Shows the cosine annealing / warm restart pattern.
    """
    history_path = Path(history_path)
    save_path = Path(save_path)

    if not history_path.exists():
        raise FileNotFoundError(f"History file not found at {history_path}")

    with open(history_path, "r") as f:
        history = json.load(f)

    epochs = history.get("epoch", [])
    lr = history.get("lr", [])

    if not epochs or not lr:
        raise ValueError("Training history lacks epoch or lr statistics.")

    fig, ax = plt.subplots(figsize=(10, 4), dpi=150)

    ax.plot(epochs, lr, color=COLORS["info"], linewidth=2.0, marker="o", markersize=3,
            markevery=max(1, len(epochs)//15))
    ax.fill_between(epochs, 0, lr, color=COLORS["info"], alpha=0.08)

    ax.set_title("Learning Rate Schedule", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Epoch", fontsize=11, labelpad=10)
    ax.set_ylabel("Learning Rate", fontsize=11, labelpad=10)
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
    ax.ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 3: Feature Importance (Top N)
# ──────────────────────────────────────────────
def plot_feature_importance(importance_dict: Dict[str, float], save_path: Union[str, Path], top_n: int = 15):
    """
    Horizontal bar chart of top-N LightGBM feature importances.
    """
    save_path = Path(save_path)

    sorted_features = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)[:top_n]
    if not sorted_features:
        return

    features, scores = zip(*reversed(sorted_features))

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    # Gradient from light to dark blue
    colors = plt.cm.Blues(np.linspace(0.35, 0.85, len(features)))

    bars = ax.barh(features, scores, color=colors, height=0.65, edgecolor="#cbd5e1", linewidth=0.6)

    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.grid(visible=False, axis="y")

    # Value annotations
    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + (max(scores) * 0.01),
            bar.get_y() + bar.get_height() / 2,
            f"{width:.2%}",
            ha="left", va="center", fontsize=9, fontweight="medium", color="#475569"
        )

    ax.set_title("LightGBM Feature Importance (Gain)", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Relative Importance", fontsize=11, labelpad=10)
    ax.set_xlim(0, max(scores) * 1.15)
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 4: Actual vs Predicted Time Series
# ──────────────────────────────────────────────
def plot_predictions_vs_actuals(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    product_name: str,
    save_path: Union[str, Path],
    lstm_pred: np.ndarray = None,
    lgbm_pred: np.ndarray = None,
):
    """
    Time-series line plot comparing actual vs forecast prices.
    Overlays LSTM, LightGBM, and Hybrid Ensemble predictions.
    """
    save_path = Path(save_path)

    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=150)
    steps = np.arange(1, len(y_true) + 1)

    # Actual
    ax.plot(steps, y_true, label="Actual", color=COLORS["actual"],
            linewidth=2.5, marker="o", markersize=4, zorder=5)

    # LSTM
    if lstm_pred is not None:
        ax.plot(steps, lstm_pred, label="LSTM", color=COLORS["lstm"],
                linewidth=1.5, linestyle="--", alpha=0.8, marker="^", markersize=3)

    # LightGBM
    if lgbm_pred is not None:
        ax.plot(steps, lgbm_pred, label="LightGBM", color=COLORS["lgbm"],
                linewidth=1.5, linestyle="--", alpha=0.8, marker="s", markersize=3)

    # Hybrid Ensemble
    ax.plot(steps, y_pred, label="Hybrid Ensemble", color=COLORS["hybrid"],
            linewidth=2.5, marker="D", markersize=4, zorder=6)

    ax.set_title(f"Predicted vs Actual: {product_name}", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Forecast Step (Days)", fontsize=11, labelpad=10)
    ax.set_ylabel("Price Index", fontsize=11, labelpad=10)

    margin = (max(y_true) - min(y_true)) * 0.20 if len(y_true) > 1 else 2.0
    ax.set_ylim(min(y_true) - margin, max(y_true) + margin)

    ax.legend(loc="upper left", framealpha=0.95)
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 5: Residual (Error) Distribution
# ──────────────────────────────────────────────
def plot_residual_distribution(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    save_path: Union[str, Path],
    model_name: str = "Model",
):
    """
    Histogram of prediction residuals (predicted - actual).
    Shows whether errors are normally distributed and unbiased.
    """
    save_path = Path(save_path)
    residuals = np.asarray(y_pred) - np.asarray(y_true)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    ax.hist(residuals, bins=50, color=COLORS["primary"], alpha=0.7,
            edgecolor="#ffffff", linewidth=0.8, density=True, label="Residuals")

    # Overlay a KDE-like normal curve
    mu, sigma = np.mean(residuals), np.std(residuals)
    x_range = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 200)
    normal_curve = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_range - mu) / sigma) ** 2)
    ax.plot(x_range, normal_curve, color=COLORS["danger"], linewidth=2.0, label=f"Normal (μ={mu:.2f}, σ={sigma:.2f})")

    ax.axvline(0, color="#1e293b", linestyle="--", linewidth=1.5, alpha=0.6, label="Zero Error")
    ax.axvline(mu, color=COLORS["warning"], linestyle="-.", linewidth=1.5, alpha=0.7, label=f"Mean = {mu:.2f}")

    ax.set_title(f"Residual Distribution — {model_name}", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Residual (Predicted − Actual)", fontsize=11, labelpad=10)
    ax.set_ylabel("Density", fontsize=11, labelpad=10)
    ax.legend(loc="upper right", framealpha=0.95)
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 6: Per-Category Metrics Bar Chart
# ──────────────────────────────────────────────
def plot_per_category_metrics(
    category_metrics: List[Dict],
    save_path: Union[str, Path],
):
    """
    Grouped bar chart showing RMSE, MAE, MAPE per product category.
    """
    save_path = Path(save_path)

    if not category_metrics:
        return

    categories = [m["product_category"] for m in category_metrics]
    rmse_vals = [m["rmse"] for m in category_metrics]
    mae_vals = [m["mae"] for m in category_metrics]
    mape_vals = [m["mape"] for m in category_metrics]

    x = np.arange(len(categories))
    bar_width = 0.25

    fig, ax1 = plt.subplots(figsize=(12, 6), dpi=150)

    bars1 = ax1.bar(x - bar_width, rmse_vals, bar_width, label="RMSE",
                    color=COLORS["primary"], edgecolor="#ffffff", linewidth=0.5)
    bars2 = ax1.bar(x, mae_vals, bar_width, label="MAE",
                    color=COLORS["secondary"], edgecolor="#ffffff", linewidth=0.5)

    ax1.set_xlabel("Category", fontsize=11, labelpad=10)
    ax1.set_ylabel("Error (Price Units)", fontsize=11, labelpad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, rotation=35, ha="right", fontsize=9)

    # Secondary y-axis for MAPE (percentage)
    ax2 = ax1.twinx()
    bars3 = ax2.bar(x + bar_width, mape_vals, bar_width, label="MAPE (%)",
                    color=COLORS["warning"], edgecolor="#ffffff", linewidth=0.5)
    ax2.set_ylabel("MAPE (%)", fontsize=11, labelpad=10, color=COLORS["warning"])
    ax2.tick_params(axis="y", labelcolor=COLORS["warning"])

    # Combined legend
    all_bars = [bars1, bars2, bars3]
    all_labels = [b.get_label() for b in all_bars]
    ax1.legend(all_bars, all_labels, loc="upper left", framealpha=0.95)

    ax1.set_title("Model Performance by Category", fontsize=14, fontweight="bold", pad=15)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)
    ax1.grid(visible=False, axis="x")
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 7: Model Comparison Bar Chart
# ──────────────────────────────────────────────
def plot_model_comparison(
    metrics: Dict[str, Dict[str, float]],
    save_path: Union[str, Path],
):
    """
    Side-by-side bar chart comparing RMSE, MAE, MAPE across
    LSTM, LightGBM, and Hybrid Ensemble.

    Args:
        metrics: {"lgbm": {"rmse":..., "mae":..., "mape":...},
                  "lstm": {...}, "ensemble": {...}}
    """
    save_path = Path(save_path)

    model_names = []
    model_colors = []
    rmse_vals, mae_vals, mape_vals = [], [], []

    label_map = {"lgbm": "LightGBM", "lstm": "LSTM", "ensemble": "Hybrid Ensemble"}
    color_map = {"lgbm": COLORS["lgbm"], "lstm": COLORS["lstm"], "ensemble": COLORS["hybrid"]}

    for key in ["lstm", "lgbm", "ensemble"]:
        if key in metrics and metrics[key]:
            model_names.append(label_map[key])
            model_colors.append(color_map[key])
            rmse_vals.append(metrics[key].get("rmse", 0))
            mae_vals.append(metrics[key].get("mae", 0))
            mape_vals.append(metrics[key].get("mape", 0))

    if not model_names:
        return

    x = np.arange(len(model_names))
    bar_width = 0.25

    fig, ax1 = plt.subplots(figsize=(10, 5.5), dpi=150)

    # RMSE bars
    bars_rmse = ax1.bar(x - bar_width, rmse_vals, bar_width, label="RMSE",
                        color=[c for c in model_colors], edgecolor="#ffffff", linewidth=0.8, alpha=0.9)
    # MAE bars (lighter shade)
    bars_mae = ax1.bar(x, mae_vals, bar_width, label="MAE",
                       color=[c for c in model_colors], edgecolor="#ffffff", linewidth=0.8, alpha=0.55)

    ax1.set_ylabel("Error (Price Units)", fontsize=11, labelpad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(model_names, fontsize=11)

    # MAPE on secondary axis
    ax2 = ax1.twinx()
    bars_mape = ax2.bar(x + bar_width, mape_vals, bar_width, label="MAPE (%)",
                        color=[c for c in model_colors], edgecolor="#1e293b", linewidth=0.8, alpha=0.3,
                        hatch="//")
    ax2.set_ylabel("MAPE (%)", fontsize=11, labelpad=10)

    # Value annotations
    for bars, vals in [(bars_rmse, rmse_vals), (bars_mae, mae_vals)]:
        for bar, val in zip(bars, vals):
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                     f"{val:.2f}", ha="center", va="bottom", fontsize=9, fontweight="medium", color="#334155")
    for bar, val in zip(bars_mape, mape_vals):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                 f"{val:.2f}%", ha="center", va="bottom", fontsize=9, fontweight="medium", color="#334155")

    # Combined legend
    ax1.legend([bars_rmse, bars_mae, bars_mape], ["RMSE", "MAE", "MAPE (%)"],
               loc="upper right", framealpha=0.95)

    ax1.set_title("Model Comparison: LSTM vs LightGBM vs Hybrid", fontsize=14, fontweight="bold", pad=15)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)
    ax1.grid(visible=False, axis="x")
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()


# ──────────────────────────────────────────────
# Plot 8: Scatter Plot (Predicted vs Actual)
# ──────────────────────────────────────────────
def plot_scatter_predicted_vs_actual(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    save_path: Union[str, Path],
    model_name: str = "Model",
    category_labels: Optional[np.ndarray] = None,
):
    """
    Scatter plot of predicted vs actual values with the y=x perfect-prediction line.
    Optionally colors points by category.
    """
    save_path = Path(save_path)
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)

    if category_labels is not None:
        unique_cats = sorted(set(category_labels))
        cmap = plt.cm.get_cmap("tab10", len(unique_cats))
        for i, cat in enumerate(unique_cats):
            mask = category_labels == cat
            ax.scatter(y_true[mask], y_pred[mask], s=20, alpha=0.5,
                       color=cmap(i), label=cat, edgecolors="none")
        ax.legend(loc="upper left", fontsize=8, framealpha=0.95, title="Category", title_fontsize=9)
    else:
        ax.scatter(y_true, y_pred, s=20, alpha=0.4, color=COLORS["primary"], edgecolors="none")

    # Perfect prediction line
    min_val = min(y_true.min(), y_pred.min())
    max_val = max(y_true.max(), y_pred.max())
    margin = (max_val - min_val) * 0.05
    ax.plot([min_val - margin, max_val + margin],
            [min_val - margin, max_val + margin],
            color=COLORS["danger"], linestyle="--", linewidth=1.5, label="Perfect Prediction (y=x)")

    # R² annotation
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    ax.text(0.05, 0.92, f"R² = {r2:.4f}", transform=ax.transAxes,
            fontsize=12, fontweight="bold", color=COLORS["primary"],
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#eff6ff", edgecolor=COLORS["primary"], alpha=0.8))

    ax.set_xlim(min_val - margin, max_val + margin)
    ax.set_ylim(min_val - margin, max_val + margin)
    ax.set_aspect("equal", adjustable="box")

    ax.set_title(f"Predicted vs Actual — {model_name}", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Actual Price Index", fontsize=11, labelpad=10)
    ax.set_ylabel("Predicted Price Index", fontsize=11, labelpad=10)
    if category_labels is None:
        ax.legend(loc="lower right", framealpha=0.95)
    plt.tight_layout()

    save_path.parent.mkdir(exist_ok=True, parents=True)
    plt.savefig(str(save_path), facecolor="#ffffff", edgecolor="none", bbox_inches="tight")
    plt.close()
