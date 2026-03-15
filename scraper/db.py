from supabase import create_client
import os

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"]
)

def insert_prices(rows):

    for r in rows:

        supabase.table("food_prices").insert(r).execute()