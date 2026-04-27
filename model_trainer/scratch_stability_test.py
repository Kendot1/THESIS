"""
Test: verify prediction stabilization across multiple products and horizons.
"""
import requests

BASE = "http://127.0.0.1:8000"

# First, get available products
resp = requests.get(f"{BASE}/predictions/products")
products_data = resp.json()["products"]
product_names = [p["product_name"] for p in products_data[:5]]  # test first 5

print(f"Testing stabilization on {len(product_names)} products: {product_names}\n")

for product in product_names:
    print(f"{'='*60}")
    print(f" {product}")
    print(f"{'='*60}")

    for horizon in ["daily", "weekly", "monthly"]:
        resp = requests.post(f"{BASE}/predictions/", json={
            "product_name": product,
            "horizon": horizon,
        })
        if resp.status_code != 200:
            print(f"  [{horizon}] ERROR {resp.status_code}")
            continue

        data = resp.json()
        current = data["current_price"]
        preds = data["predictions"]

        prices = [p["predicted_price"] for p in preds]
        if not prices:
            print(f"  [{horizon}] No predictions returned")
            continue

        total_change_pct = (prices[-1] - current) / current * 100 if current else 0

        # Check for exponential growth
        max_step_change = 0
        prev = current
        for p in prices:
            step_change = abs(p - prev) / prev * 100 if prev else 0
            max_step_change = max(max_step_change, step_change)
            prev = p

        trajectory = " -> ".join([f"{current:.1f}"] + [f"{p:.1f}" for p in prices[:7]])
        if len(prices) > 7:
            trajectory += f" -> ... -> {prices[-1]:.1f}"

        status = "OK" if abs(total_change_pct) <= 20 else "WARN"
        print(f"  [{horizon:7s}] {status} {trajectory}")
        print(f"           Total: {total_change_pct:+.1f}%  |  Max step: {max_step_change:.1f}%  |  Steps: {len(prices)}")
