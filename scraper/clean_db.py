import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from supabase import create_client

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def clean_duplicates():
    print("Fetching all food_prices...")
    
    # Fetch all data
    all_data = []
    page_size = 1000
    start_idx = 0
    while True:
        response = supabase.table("food_prices").select("*").range(start_idx, start_idx + page_size - 1).execute()
        data = response.data
        if not data:
            break
        all_data.extend(data)
        if len(data) < page_size:
            break
        start_idx += page_size
        
    print(f"Total rows fetched: {len(all_data)}")
    
    # Group by (product_name, origin, report_date)
    grouped = {}
    for row in all_data:
        # treat None as "null_variant" to distinguish it safely
        v = row.get("product_variant")
        key = (row["product_name"], row["origin"], row["report_date"])
        grouped.setdefault(key, []).append(row)
        
    to_delete_ids = []
    to_update_ids = []
    
    for key, rows in grouped.items():
        if len(rows) > 1:
            # We have duplicates!
            has_standard = any(r.get("product_variant") == "Standard" for r in rows)
            has_null = any(not r.get("product_variant") or r.get("product_variant").lower() == "null" for r in rows)
            
            if has_standard and has_null:
                # Delete the null ones
                for r in rows:
                    if not r.get("product_variant") or r.get("product_variant").lower() == "null":
                        to_delete_ids.append(r["id"])
            elif has_null:
                # Multiple nulls? Just keep one, delete the rest, and update the one to "Standard"
                null_rows = [r for r in rows if not r.get("product_variant") or r.get("product_variant").lower() == "null"]
                for r in null_rows[1:]:
                    to_delete_ids.append(r["id"])
                to_update_ids.append(null_rows[0]["id"])
        else:
            # Only 1 row
            r = rows[0]
            if not r.get("product_variant") or r.get("product_variant").lower() == "null":
                to_update_ids.append(r["id"])
                
    print(f"Found {len(to_delete_ids)} duplicate rows to delete.")
    print(f"Found {len(to_update_ids)} single null rows to update to 'Standard'.")
    
    # Execute Deletions
    if to_delete_ids:
        print("Deleting duplicates...")
        for i in range(0, len(to_delete_ids), 100):
            batch = to_delete_ids[i:i+100]
            supabase.table("food_prices").delete().in_("id", batch).execute()
            
    # Execute Updates
    if to_update_ids:
        print("Updating nulls to 'Standard'...")
        for i in range(0, len(to_update_ids), 100):
            batch = to_update_ids[i:i+100]
            supabase.table("food_prices").update({"product_variant": "Standard"}).in_("id", batch).execute()
            
    print("Database cleaning complete!")

if __name__ == "__main__":
    clean_duplicates()
