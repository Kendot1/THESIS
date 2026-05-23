"""
Evaluation-specific plot generation (called by `python main.py evaluate`).
Uses only matplotlib — no seaborn dependency required.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from utils.logger import get_logger

log = get_logger(__name__)


def generate_evaluation_plots(test_df: pd.DataFrame, report: dict, output_dir: str = "plots"):
    """
    Generate and save evaluation plots locally.
    Creates: scatter plot, error distribution, MAPE by category, highest error products.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    log.info(f"Generating evaluation plots in {output_dir}/ ...")

    # Style
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"]

    # 1. Actual vs Predicted Scatter Plot (Overall)
    try:
        fig, ax = plt.subplots(figsize=(10, 8), dpi=150)

        categories = test_df["product_category"].unique()
        cmap = plt.cm.get_cmap("tab10", len(categories))
        for i, cat in enumerate(sorted(categories)):
            mask = test_df["product_category"] == cat
            ax.scatter(
                test_df.loc[mask, "price_index"],
                test_df.loc[mask, "predicted_price"],
                s=20, alpha=0.5, color=cmap(i), label=cat, edgecolors="none"
            )

        min_val = min(test_df["price_index"].min(), test_df["predicted_price"].min())
        max_val = max(test_df["price_index"].max(), test_df["predicted_price"].max())
        ax.plot([min_val, max_val], [min_val, max_val], "r--", lw=1.5, label="Perfect Prediction")

        ax.set_title("Actual vs Predicted Prices (Hybrid Ensemble)", fontsize=14, fontweight="bold")
        ax.set_xlabel("Actual Price", fontsize=11)
        ax.set_ylabel("Predicted Price", fontsize=11)
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "actual_vs_predicted_overall.png"), dpi=300,
                    facecolor="#ffffff", bbox_inches="tight")
        plt.close()
        log.info("  -> actual_vs_predicted_overall.png")
    except Exception as e:
        log.error(f"Failed to generate scatter plot: {e}")

    # 2. Error Distribution
    try:
        test_df = test_df.copy()
        test_df["error"] = test_df["predicted_price"] - test_df["price_index"]

        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
        ax.hist(test_df["error"], bins=50, color="#2563eb", alpha=0.7, edgecolor="#ffffff", linewidth=0.5, density=True)

        mu, sigma = test_df["error"].mean(), test_df["error"].std()
        x_range = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 200)
        normal_curve = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_range - mu) / sigma) ** 2)
        ax.plot(x_range, normal_curve, color="#dc2626", linewidth=2.0, label=f"Normal (μ={mu:.2f}, σ={sigma:.2f})")

        ax.axvline(0, color="#1e293b", linestyle="--", lw=1.5, alpha=0.6, label="Zero Error")
        ax.set_title("Prediction Error Distribution (Hybrid Ensemble)", fontsize=14, fontweight="bold")
        ax.set_xlabel("Error (Predicted − Actual)", fontsize=11)
        ax.set_ylabel("Density", fontsize=11)
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "error_distribution.png"), dpi=300, facecolor="#ffffff")
        plt.close()
        log.info("  -> error_distribution.png")
    except Exception as e:
        log.error(f"Failed to generate error distribution plot: {e}")

    # 3. MAPE per Category
    try:
        if "per_category" in report and report["per_category"]:
            cat_df = pd.DataFrame(report["per_category"])
            cat_df = cat_df.sort_values("mape", ascending=True)

            fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
            colors = plt.cm.Blues(np.linspace(0.4, 0.85, len(cat_df)))
            ax.barh(cat_df["product_category"], cat_df["mape"], color=colors, height=0.6, edgecolor="#cbd5e1")

            for i, (_, row) in enumerate(cat_df.iterrows()):
                ax.text(row["mape"] + 0.05, i, f"{row['mape']:.2f}%", va="center", fontsize=9, color="#475569")

            ax.set_title("MAPE by Category (Hybrid Ensemble)", fontsize=14, fontweight="bold")
            ax.set_xlabel("MAPE (%)", fontsize=11)
            ax.grid(axis="x", linestyle="--", alpha=0.4)
            ax.grid(visible=False, axis="y")
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, "mape_by_category.png"), dpi=300, facecolor="#ffffff")
            plt.close()
            log.info("  -> mape_by_category.png")
    except Exception as e:
        log.error(f"Failed to generate MAPE by category plot: {e}")

    # 4. Top 15 Products by MAPE
    try:
        if "per_product" in report and report["per_product"]:
            prod_df = pd.DataFrame(report["per_product"])
            prod_df = prod_df.sort_values("mape", ascending=False).head(15)
            prod_df = prod_df.sort_values("mape", ascending=True)  # reverse for barh

            fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
            colors = plt.cm.Reds(np.linspace(0.3, 0.8, len(prod_df)))
            ax.barh(prod_df["product_name"], prod_df["mape"], color=colors, height=0.6, edgecolor="#cbd5e1")

            for i, (_, row) in enumerate(prod_df.iterrows()):
                ax.text(row["mape"] + 0.05, i, f"{row['mape']:.2f}%", va="center", fontsize=9, color="#475569")

            ax.set_title("Top 15 Products with Highest MAPE (Hybrid Ensemble)", fontsize=14, fontweight="bold")
            ax.set_xlabel("MAPE (%)", fontsize=11)
            ax.grid(axis="x", linestyle="--", alpha=0.4)
            ax.grid(visible=False, axis="y")
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, "highest_error_products.png"), dpi=300, facecolor="#ffffff")
            plt.close()
            log.info("  -> highest_error_products.png")
    except Exception as e:
        log.error(f"Failed to generate highest error products plot: {e}")

    log.info(f"All plots saved to {os.path.abspath(output_dir)}")
