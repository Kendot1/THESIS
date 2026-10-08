"""
Seed the `products` table from food_prices data.
Paginates through all records in food_prices with unit normalization.
"""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supabase import create_client
from config.settings import get_settings
from data.preprocessor import normalize_unit

cfg = get_settings()
sb = create_client(cfg.supabase_url, cfg.supabase_key)

DESCRIPTIONS = {
    "Avocado": "A nutrient-rich fruit grown primarily in Mindanao and the Cordillera region.",
    "Baguio Beans": "Highland snap beans from the Cordillera, prized for their crisp texture.",
    "Banana": "The most consumed fruit in the Philippines, available in Lakatan, Latundan, and Saba varieties.",
    "Beef": "Red meat essential for hearty Filipino stews like bulalo, caldereta, and kare-kare.",
    "Bell Pepper": "A versatile sweet pepper used in various Filipino and international dishes.",
    "Bittergourd": "Known locally as ampalaya, valued for its health benefits and bitter taste.",
    "Broccoli": "A premium highland vegetable with growing demand in NCR urban markets.",
    "Cabbage": "Leafy vegetable sourced from Benguet highlands, commonly used in soups.",
    "Calamansi": "Philippine lime essential for marinades, dipping sauces, and refreshing drinks.",
    "Carrot": "Sweet root vegetable primarily grown in the highlands of Benguet province.",
    "Cauliflower": "Highland cruciferous vegetable with supply dependent on Benguet production.",
    "Celery": "An aromatic ingredient in Filipino and Chinese cooking, from highland farms.",
    "Chayote": "A mild-flavored gourd popular in Filipino soups, primarily from Cordillera.",
    "Chicken": "The most widely consumed poultry meat, key to countless Filipino recipes.",
    "Chicken Egg": "A highly nutritious and affordable daily protein staple.",
    "Chili": "Essential for adding heat to Filipino dishes. Prices spike during shortages.",
    "Coconut Oil": "A cooking staple from coconuts. The Philippines is a major global producer.",
    "Corn": "A major agricultural product consumed boiled, roasted, or as milled staple.",
    "Corn Cracked": "Cracked corn widely used as poultry and livestock feed.",
    "Corn Grits": "A processed corn product used in food manufacturing.",
    "Eggplant": "A versatile vegetable famously grilled for tortang talong or stewed in pinakbet.",
    "Garlic": "An essential aromatic spice in Filipino cooking, mostly imported.",
    "Ginger": "A zesty rhizome used in broths like arroz caldo and to flavor meat dishes.",
    "Lettuce": "A temperature-sensitive leafy vegetable grown in highland areas.",
    "Mango": "Carabao mangoes, world-renowned for exceptional sweetness and smooth texture.",
    "Melon": "Cantaloupe and honeydew varieties consumed fresh, with seasonal pricing.",
    "Milkfish": "Bangus, the national fish of the Philippines, a major aquaculture product.",
    "Palm Oil": "An imported cooking oil widely used in food manufacturing.",
    "Papaya": "A tropical fruit available year-round. Green papaya is used in tinola.",
    "Pechay Baguio": "Highland Chinese cabbage popular in soups.",
    "Pechay Tagalog": "Lowland pechay variety widely grown across Luzon.",
    "Pomelo": "A large citrus fruit popular during holidays.",
    "Pork": "The most widely consumed meat in the Philippines, featured in adobo and lechon.",
    "Potato": "A highland tuber crop used as a hearty addition to Filipino dishes.",
    "Red Onion": "A key cooking ingredient across Filipino cuisine, highly volatile in pricing.",
    "Rice": "The foundational staple grain of the Philippine diet, eaten with nearly every meal.",
    "Round Scad": "Galunggong, a pelagic fish that is a dietary staple for many households.",
    "Salmon Head": "Imported salmon parts popular in sinigang and Filipino soup dishes.",
    "Sardines": "An affordable protein source available fresh or canned.",
    "Squash": "Kalabasa, a nutrient-dense gourd commonly cooked with coconut milk.",
    "Squid": "A popular seafood ingredient used in adobo and grilled dishes.",
    "String Beans": "Sitao or yardlong beans, common in pinakbet, sinigang, and kare-kare.",
    "Sugar": "Produced primarily in the Visayas, with prices regulated by quotas.",
    "Tilapia": "A popular freshwater fish farmed extensively in Central Luzon.",
    "Tomato": "A vital base ingredient providing acidity and umami to Filipino stews.",
    "Watermelon": "A popular summer fruit with prices dropping during peak harvest.",
    "White Onion": "Milder-flavored onion variety, typically imported.",
    "Yellow Sweet Corn": "A popular vegetable corn variety consumed as snack or ingredient.",
}


def fetch_batch_combos(range_tuple):
    start, end = range_tuple
    client = create_client(cfg.supabase_url, cfg.supabase_key)
    res = client.table("food_prices").select(
        "product_name, product_variant, origin, product_category, unit"
    ).range(start, end).execute()
    return res.data


def main():
    print("=" * 60)
    print("Transferring products from food_prices to products table")
    print("=" * 60)

    # 1. Determine total count in food_prices
    count_res = sb.table("food_prices").select("id", count="exact").limit(1).execute()
    total_records = count_res.count or 0
    print(f"Total food_prices records to scan: {total_records:,}")

    if total_records == 0:
        print("No records found in food_prices. Exiting.")
        return

    # 2. Paginate across all records in parallel
    batch_size = 1000
    ranges = [(i, min(i + batch_size - 1, total_records - 1)) for i in range(0, total_records, batch_size)]
    print(f"Paginating {len(ranges)} batches across food_prices...")

    combos = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        for batch_data in executor.map(fetch_batch_combos, ranges):
            for row in batch_data:
                name = row.get("product_name")
                if not name:
                    continue
                name = name.strip()
                if not name or name.lower() == "unknown":
                    continue

                variant = (row.get("product_variant") or "").strip()
                if not variant or variant.lower() in ("unknown", "null"):
                    variant = "Standard"

                origin = (row.get("origin") or "").strip()
                if not origin:
                    origin = "Unknown"

                category = (row.get("product_category") or "").strip()
                if not category or category.lower() == "unknown":
                    continue

                unit = normalize_unit(row.get("unit"))
                if category == "Oils" and variant.lower() == "1l":
                    unit = "liter"
                elif category == "Oils" and variant.lower() == "350ml":
                    unit = "350ml"
                elif name == "Chicken Egg":
                    unit = "piece"

                if not unit or unit == "unknown":
                    continue

                key = (name, variant, origin, unit)
                if key not in combos:
                    combos[key] = category

    print(f"Found {len(combos)} unique product series across food_prices.")
    print("Upserting into products table...")

    inserted = 0
    for (name, variant, origin, unit), category in sorted(combos.items()):
        desc = DESCRIPTIONS.get(name, f"{name} is a tracked commodity in the NCR agri-fishery market.")
        try:
            sb.table("products").upsert({
                "name": name,
                "variant": variant,
                "origin": origin,
                "category": category,
                "unit": unit,
                "description": desc,
                "image_url": "",
            }, on_conflict="name,variant,origin,unit").execute()
            inserted += 1
        except Exception as e:
            print(f"  FAIL {name} | {variant} | {origin} | {unit}: {e}")

    print(f"Successfully upserted {inserted}/{len(combos)} products.")

    # 3. Verification
    r = sb.table("products").select("id, name, variant, origin, category, unit").order("name").execute()
    print(f"\nVerification: {len(r.data)} total rows in products table.")
    for p in r.data[:8]:
        v = p.get("variant") or "-"
        o = p.get("origin") or "-"
        u = p.get("unit") or "-"
        id_str = str(p['id'])[:8] + "..."
        print(f"  id={id_str:11s} | {p['category']:12s} | {p['name']:20s} | {v:20s} | {o:10s} | {u}")
    if len(r.data) > 8:
        print(f"  ... and {len(r.data) - 8} more")
    print("\nTransfer complete!")


if __name__ == "__main__":
    main()
