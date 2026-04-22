import os
from supabase import create_client

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def insert_prices(rows):
    """
    Insert rows into Supabase, avoiding duplicates by product + variant + origin + date.
    Normalizes product_variant so None, "", and "null" are all treated as None.
    """
    seen = set()
    for row in rows:
        # Normalize product_variant: treat empty string / "null" string as None
        variant = row.get("product_variant")
        if not variant or str(variant).strip().lower() == "null":
            row["product_variant"] = None
            variant = None

        key = (row["product_name"], variant, row["origin"], row["report_date"])
        if key in seen:
            continue
        seen.add(key)
        try:
            supabase.table("food_prices").insert(row).execute()
        except Exception as e:
            print(f"Failed to insert row: {row} - {e}")