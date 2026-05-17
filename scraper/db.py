import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from supabase import create_client

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def insert_prices(rows):
    """
    Insert rows into Supabase, avoiding duplicates by product + variant + origin + date.
    Normalizes product_variant so None, "", and "null" are all treated as None.
    """
    seen = set()
    for row in rows:
        # Normalize product_variant: treat empty string / "null" string as "Standard"
        variant = row.get("product_variant")
        if not variant or str(variant).strip().lower() == "null" or str(variant).strip().lower() == "none":
            row["product_variant"] = "Standard"
            variant = "Standard"

        key = (row["product_name"], variant, row["origin"], row["report_date"])
        if key in seen:
            continue
        seen.add(key)
        try:
            # Use upsert to overwrite any copied/placeholder data with actual scraped data
            supabase.table("food_prices").upsert(row, on_conflict="product_name,product_variant,origin,report_date").execute()
        except Exception as e:
            print(f"Failed to upsert row: {row} - {e}")

def get_last_date():
    try:
        response = supabase.table("food_prices").select("report_date").order("report_date", desc=True).limit(1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["report_date"]
        return None
    except Exception as e:
        print(f"Failed to fetch last date: {e}")
        return None

def get_processed_pdfs():
    try:
        processed = set()
        page_size = 1000
        start_idx = 0
        while True:
            response = supabase.table("food_prices").select("source_pdf").range(start_idx, start_idx + page_size - 1).execute()
            if not response.data:
                break
            processed.update(row["source_pdf"] for row in response.data if row.get("source_pdf"))
            if len(response.data) < page_size:
                break
            start_idx += page_size
        return processed
    except Exception as e:
        print(f"Failed to fetch processed PDFs: {e}")
        return set()