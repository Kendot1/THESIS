import requests

try:
    resp = requests.post("http://127.0.0.1:8000/predictions/", json={"product_name": "Tomato", "horizon": "daily"})
    print("Predictions Status:", resp.status_code)
    print(resp.json())
except Exception as e:
    print(f"Predictions failed: {e}")

try:
    resp = requests.post("http://127.0.0.1:8000/explanations/", json={"product_name": "Tomato", "horizon": "daily"})
    print("Explanations Status:", resp.status_code)
    print(resp.json())
except Exception as e:
    print(f"Explanations failed: {e}")
