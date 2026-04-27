import requests, json

r = requests.post("http://localhost:8000/predictions/", json={
    "product_name": "Banana",
    "product_variant": "Saba",
    "horizon": "weekly"
})
d = r.json()
print(f"Current price: {d['current_price']}")
print("---")
for p in d["predictions"]:
    print(f"{p['date']}: {p['predicted_price']}  ({p['lower_bound']} - {p['upper_bound']})")
