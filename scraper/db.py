import os
from supabase import create_client

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def insert_prices(rows):
    """
    Insert rows into Supabase, avoiding duplicates by product + variant + origin + date
    """
    seen = set()
    for row in rows:
        key = (row["product_name"], row["product_variant"], row["origin"], row["report_date"])
        if key in seen:
            continue
        seen.add(key)
        try:
            supabase.table("food_prices").insert(row).execute()
        except Exception as e:
            print(f"Failed to insert row: {row} - {e}")