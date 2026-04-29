import sys, os
from dotenv import dotenv_values
from supabase import create_client

env_vars = dotenv_values('../foodcast/.env.local')
sb = create_client(env_vars.get('NEXT_PUBLIC_SUPABASE_URL'), env_vars.get('NEXT_PUBLIC_SUPABASE_ANON_KEY'))

r = sb.table('food_prices').select('*').eq('price_index', 351.14).execute()
for row in r.data:
    print(f"{row['report_date']} | {row['product_name']} | {row['product_variant']} | {row['origin']}")
