import sys, os
from dotenv import dotenv_values
from supabase import create_client

env_vars = dotenv_values('../foodcast/.env.local')
sb = create_client(env_vars.get('NEXT_PUBLIC_SUPABASE_URL'), env_vars.get('NEXT_PUBLIC_SUPABASE_ANON_KEY'))

# Check food prices
print("--- Alumahan Prices ---")
r = sb.table('food_prices').select('*').eq('product_name', 'Alumahan').order('report_date', desc=True).limit(10).execute()
for row in r.data:
    print(f"{row['report_date']} | {row['product_variant']} | {row['origin']} | {row['price_index']}")

# Check predictions
print("\n--- Alumahan Predictions ---")
# First get product_id
p = sb.table('products').select('*').eq('name', 'Alumahan').execute()
if p.data:
    pid = p.data[0]['id']
    print(f"Product ID: {pid}")
    pr = sb.table('predictions').select('*').eq('product_id', pid).order('prediction_date').limit(10).execute()
    for row in pr.data:
        print(f"{row['prediction_date']} | {row['predicted_price']}")
