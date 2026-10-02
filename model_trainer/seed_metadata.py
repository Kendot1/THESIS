"""
Seed the `products` table from food_prices data.
Run after creating the tables via the SQL migration.
"""
import sys
sys.path.insert(0, '.')
from supabase import create_client
from config.settings import get_settings

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


def main():
    print("Fetching unique product series from food_prices...")
    r = sb.table("food_prices").select(
        "product_name, product_variant, origin, product_category, unit").execute()

    combos = {}
    for row in r.data:
        name = row["product_name"]
        variant = row.get("product_variant") or ""
        if not variant or variant.lower() == "unknown":
            variant = "Standard"
        origin = row.get("origin") or ""
        category = row["product_category"]
        unit = (row.get("unit") or "").strip().lower()
        if not unit or unit == "unknown":
            continue
        key = (name, variant, origin, unit)
        if key not in combos:
            combos[key] = category

    print(f"Found {len(combos)} unique product series. Seeding products table...")

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
            print(f"  FAIL {name} | {variant} | {origin}: {e}")

    print(f"Inserted {inserted}/{len(combos)} products.")

    # Verify
    r = sb.table("products").select("id, name, variant, origin, category").order("id").execute()
    print(f"\nVerification: {len(r.data)} rows in products table")
    for p in r.data[:5]:
        v = p.get("variant") or "-"
        o = p.get("origin") or "-"
        id_str = str(p['id'])[:8] + "..." # Truncate UUID for display
        print(f"  id={id_str:11s} | {p['category']:12s} | {p['name']:20s} | {v:30s} | {o}")
    if len(r.data) > 5:
        print(f"  ... and {len(r.data) - 5} more")
    print("\nDone!")


if __name__ == "__main__":
    main()
