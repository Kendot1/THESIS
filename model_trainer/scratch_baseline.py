import pandas as pd
import numpy as np

df = pd.read_csv("artifacts/clean_data.csv")
df = df.sort_values(["product_name", "report_date"]).reset_index(drop=True)
df["price_lag_1d"] = df.groupby("product_name")["price_index"].shift(1)

df_val = df.dropna(subset=["price_lag_1d"]).copy()
df_val = df_val.tail(1192) # approximate validation set

mape = np.mean(np.abs((df_val["price_index"] - df_val["price_lag_1d"]) / df_val["price_index"])) * 100
print(f"Naive Baseline (price_t = price_{{t-1}}) MAPE: {mape:.2f}%")
