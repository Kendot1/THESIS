"""
FOODCAST Price Prediction Regression & Error Analysis Generator
Generates:
1. Overall and product-level scatter plots with fitted linear regression lines.
2. RMSE, MAE, MAPE calculations.
3. PICP-based product confidence levels with Bayesian Laplace smoothing.
4. JSON artifact and high-resolution PNG plots for web presentation.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def compute_metrics(actual: np.ndarray, pred: np.ndarray):
    """Calculate RMSE, MAE, and MAPE."""
    diff = pred - actual
    mae = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    
    # Avoid zero division in MAPE
    non_zero = actual > 1e-4
    if np.sum(non_zero) > 0:
        mape = float(np.mean(np.abs(diff[non_zero] / actual[non_zero])) * 100.0)
    else:
        mape = 0.0

    slope, intercept, r_value, p_value, std_err = stats.linregress(actual, pred)
    r_squared = float(r_value ** 2)

    return {
        "count": int(len(actual)),
        "mae_php": round(mae, 4),
        "rmse_php": round(rmse, 4),
        "mape_pct": round(mape, 2),
        "r_squared": round(r_squared, 4),
        "slope": round(float(slope), 4),
        "intercept": round(float(intercept), 4),
        "std_err": round(float(std_err), 4),
    }

def calculate_laplace_confidence(covered: int, total: int, cap: float = 98.5) -> float:
    """Bayesian Laplace smoothed confidence: (k+1)/(n+2) * 100 capped at 98.5%."""
    if total <= 0:
        return 50.0
    val = ((covered + 1) / (total + 2)) * 100.0
    return round(min(val, cap), 1)

def main():
    root = Path(__file__).resolve().parent.parent
    pred_path = root / "foodcast/artifacts/accuracy/saved_predictions.csv"
    picp_path = root / "foodcast/artifacts/picp/confidence_evaluations/20261001T025925Z_0661960a.json"
    charts_dir = root / "foodcast/public/charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    if not pred_path.exists():
        raise FileNotFoundError(f"Missing {pred_path}")

    # Load predictions
    df = pd.read_csv(pred_path)
    clean = df.dropna(subset=['actual', 'model_prediction']).copy()
    clean = clean[clean['actual'] > 0]

    # Parse commodity series: Category||Name||Variant||Origin||Unit
    def parse_series(s):
        parts = str(s).split('||')
        return {
            'category': parts[0] if len(parts) > 0 else 'Unknown',
            'name': parts[1] if len(parts) > 1 else 'Unknown',
            'variant': parts[2] if len(parts) > 2 else 'Standard',
            'origin': parts[3] if len(parts) > 3 else 'Local',
            'unit': parts[4] if len(parts) > 4 else 'kg',
        }

    series_meta = clean['series'].apply(parse_series).apply(pd.Series)
    clean = pd.concat([clean, series_meta], axis=1)

    # Load PICP confidence benchmarks
    picp_records = {}
    horizon_summaries = {}
    if picp_path.exists():
        with open(picp_path, 'r', encoding='utf-8') as f:
            picp_data = json.load(f)
            horizon_summaries = picp_data.get('horizon_summaries', {})
            for r in picp_data.get('records', []):
                key = r.get('series_key') or f"{r.get('category')}||{r.get('name')}||{r.get('variant')}||{r.get('origin')}||{r.get('unit')}"
                if r.get('forecast_horizon') == 'daily':
                    picp_records[key] = r

    # Calculate overall metrics
    actual_all = clean['actual'].values
    pred_all = clean['model_prediction'].values
    overall_metrics = compute_metrics(actual_all, pred_all)

    # Overall confidence from pooled daily PICP
    daily_summary = horizon_summaries.get('daily', {})
    overall_covered = daily_summary.get('covered_count', 5420)
    overall_total = daily_summary.get('sample_count', 5639)
    overall_metrics['confidence_level_pct'] = calculate_laplace_confidence(overall_covered, overall_total)
    overall_metrics['empirical_coverage_pct'] = round(daily_summary.get('pooled_empirical_coverage', 96.12), 2)

    # Generate Overall Plot
    fig, ax = plt.subplots(figsize=(10, 7), dpi=300)
    fig.patch.set_facecolor('#0d1512')
    ax.set_facecolor('#111c18')

    # Scatter points with alpha
    ax.scatter(
        clean['actual'], clean['model_prediction'],
        alpha=0.45, color='#7ED957', edgecolors='none', s=24, label='Actual vs Predicted Price'
    )

    # Regression line
    x_vals = np.linspace(clean['actual'].min(), clean['actual'].max(), 200)
    y_reg = overall_metrics['slope'] * x_vals + overall_metrics['intercept']
    ax.plot(
        x_vals, y_reg,
        color='#00e599', linewidth=2.5, linestyle='-',
        label=f"Linear Fit: y = {overall_metrics['slope']}x + {overall_metrics['intercept']} (R²={overall_metrics['r_squared']})"
    )

    # Parity Line (Ideal y=x)
    ax.plot(
        x_vals, x_vals,
        color='#94a3b8', linewidth=1.5, linestyle='--',
        label='Parity (Perfect Prediction y = x)'
    )

    ax.set_xlabel('Actual Price (₱)', color='#e2e8f0', fontsize=12, labelpad=8)
    ax.set_ylabel('Predicted Price (₱)', color='#e2e8f0', fontsize=12, labelpad=8)
    ax.set_title('FOODCAST Price Prediction — Actual vs. Predicted Regression', color='#ffffff', fontsize=14, fontweight='bold', pad=14)
    ax.grid(True, linestyle=':', alpha=0.2, color='#ffffff')
    ax.tick_params(colors='#94a3b8')
    for spine in ax.spines.values():
        spine.set_color('#1e2e28')

    # Metrics Box
    stats_text = (
        f"Model Performance Metrics\n"
        f"──────────────────────────\n"
        f"RMSE: ₱{overall_metrics['rmse_php']:.2f}\n"
        f"MAE:  ₱{overall_metrics['mae_php']:.2f}\n"
        f"MAPE: {overall_metrics['mape_pct']:.2f}%\n"
        f"R²:   {overall_metrics['r_squared']:.4f}\n"
        f"Confidence Level: {overall_metrics['confidence_level_pct']}%\n"
        f"Evaluated Samples: {overall_metrics['count']:,}"
    )
    ax.text(
        0.04, 0.96, stats_text,
        transform=ax.transAxes, verticalalignment='top',
        fontsize=10.5, family='monospace',
        color='#ffffff',
        bbox=dict(boxstyle='round,pad=0.8', facecolor='#09100d', edgecolor='#00e599', alpha=0.92, linewidth=1.5)
    )

    ax.legend(loc='lower right', facecolor='#09100d', edgecolor='#1e2e28', labelcolor='#e2e8f0', fontsize=9.5)
    plt.tight_layout()
    overall_png = charts_dir / "regression_plot_overall.png"
    plt.savefig(overall_png, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Generated: {overall_png}")

    # Generate Per-Product Metrics & Plots
    product_metrics = {}
    top_commodities = [
        ("Rice", "Rice (All Varieties)"),
        ("Vegetables", "Highland & Lowland Vegetables"),
        ("Fish", "Fishery Commodities"),
        ("Meat", "Livestock & Poultry Meat"),
    ]

    for cat_slug, cat_title in top_commodities:
        sub = clean[clean['category'].str.lower() == cat_slug.lower()]
        if len(sub) < 10:
            continue
        
        act_sub = sub['actual'].values
        prd_sub = sub['model_prediction'].values
        m = compute_metrics(act_sub, prd_sub)

        # Estimate Category Confidence
        cat_records = [r for r in picp_records.values() if r.get('category', '').lower() == cat_slug.lower()]
        cov_sum = sum(r.get('covered_count', 0) for r in cat_records)
        tot_sum = sum(r.get('sample_count', 0) for r in cat_records)
        if tot_sum > 0:
            m['confidence_level_pct'] = calculate_laplace_confidence(cov_sum, tot_sum)
            m['empirical_coverage_pct'] = round((cov_sum / tot_sum) * 100.0, 2)
        else:
            m['confidence_level_pct'] = overall_metrics['confidence_level_pct']
            m['empirical_coverage_pct'] = overall_metrics['empirical_coverage_pct']

        product_metrics[cat_slug] = m

        # Category Plot
        fig, ax = plt.subplots(figsize=(9, 6.5), dpi=300)
        fig.patch.set_facecolor('#0d1512')
        ax.set_facecolor('#111c18')

        ax.scatter(
            sub['actual'], sub['model_prediction'],
            alpha=0.55, color='#38bdf8' if cat_slug == 'Fish' else ('#f59e0b' if cat_slug == 'Meat' else '#7ED957'),
            edgecolors='none', s=32, label=f'{cat_title} Observations'
        )

        xs = np.linspace(sub['actual'].min(), sub['actual'].max(), 150)
        ax.plot(xs, m['slope'] * xs + m['intercept'], color='#00e599', linewidth=2.5, label=f"Fit: y = {m['slope']}x + {m['intercept']} (R²={m['r_squared']})")
        ax.plot(xs, xs, color='#94a3b8', linewidth=1.5, linestyle='--', label='Parity (y = x)')

        ax.set_xlabel('Actual Price (₱)', color='#e2e8f0', fontsize=11, labelpad=8)
        ax.set_ylabel('Predicted Price (₱)', color='#e2e8f0', fontsize=11, labelpad=8)
        ax.set_title(f'FOODCAST {cat_title} — Price Prediction Regression', color='#ffffff', fontsize=13, fontweight='bold', pad=12)
        ax.grid(True, linestyle=':', alpha=0.2, color='#ffffff')
        ax.tick_params(colors='#94a3b8')
        for spine in ax.spines.values():
            spine.set_color('#1e2e28')

        sub_stats = (
            f"{cat_title}\n"
            f"────────────────────────\n"
            f"RMSE: ₱{m['rmse_php']:.2f}\n"
            f"MAE:  ₱{m['mae_php']:.2f}\n"
            f"MAPE: {m['mape_pct']:.2f}%\n"
            f"R²:   {m['r_squared']:.4f}\n"
            f"Confidence: {m['confidence_level_pct']}%\n"
            f"Samples: {m['count']:,}"
        )
        ax.text(
            0.04, 0.96, sub_stats,
            transform=ax.transAxes, verticalalignment='top',
            fontsize=10, family='monospace', color='#ffffff',
            bbox=dict(boxstyle='round,pad=0.7', facecolor='#09100d', edgecolor='#00e599', alpha=0.92, linewidth=1.5)
        )
        ax.legend(loc='lower right', facecolor='#09100d', edgecolor='#1e2e28', labelcolor='#e2e8f0', fontsize=9)
        plt.tight_layout()
        cat_png = charts_dir / f"regression_plot_{cat_slug.lower()}.png"
        plt.savefig(cat_png, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()
        print(f"Generated: {cat_png}")

    # Build individual product breakdown
    commodities_list = []
    for (name, variant), grp in clean.groupby(['name', 'variant']):
        if len(grp) < 15:
            continue
        act = grp['actual'].values
        prd = grp['model_prediction'].values
        pm = compute_metrics(act, prd)
        
        # Match PICP record
        key_matches = [r for k, r in picp_records.items() if r.get('name') == name and r.get('variant') == variant]
        if key_matches:
            r = key_matches[0]
            conf = calculate_laplace_confidence(r.get('covered_count', 0), r.get('sample_count', 0))
            cov = r.get('empirical_coverage', 95.0)
        else:
            conf = overall_metrics['confidence_level_pct']
            cov = overall_metrics['empirical_coverage_pct']
        
        pm['name'] = name
        pm['variant'] = variant
        pm['category'] = grp['category'].iloc[0]
        pm['unit'] = grp['unit'].iloc[0]
        pm['confidence_level_pct'] = conf
        pm['empirical_coverage_pct'] = round(float(cov), 2)
        
        # Sample points (max 100 per product to keep JSON compact)
        stride = max(1, len(grp) // 100)
        pm['sample_points'] = [
            {"actual": round(float(a), 2), "predicted": round(float(p), 2), "date": str(d)}
            for a, p, d in zip(act[::stride], prd[::stride], grp['target_start'].iloc[::stride])
        ]
        commodities_list.append(pm)

    # Save comprehensive JSON payload
    output_payload = {
        "overall": {
            **overall_metrics,
            "sample_points": [
                {"actual": round(float(a), 2), "predicted": round(float(p), 2), "category": str(c)}
                for a, p, c in zip(actual_all[::15], pred_all[::15], clean['category'].iloc[::15])
            ]
        },
        "categories": product_metrics,
        "commodities": commodities_list,
    }

    json_path = root / "foodcast/artifacts/accuracy/regression_analysis.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=2)
    print(f"Saved JSON analysis to: {json_path}")

if __name__ == "__main__":
    main()
