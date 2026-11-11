import os
import json
import math
import re
import time
from google import genai

CATEGORY_LIST = ["Rice", "Corn", "Poultry", "Livestock", "Vegetables",
                 "Fruits", "Fish", "Oils", "Sugar"]

# FOODCAST names used to keep Daily Price Index rows consistent across dates.
PRODUCT_VARIANT_REF = """
CANONICAL FOODCAST PRODUCT REFERENCE:
| product_name     | product_variant examples                                      | product_category |
|------------------|---------------------------------------------------------------|------------------|
| Rice             | Kadiwa (Benteng Bigas), Basmati, Glutinous, Jasponica/Japonica, Other Special Rice, Regular Milled, Well Milled, Premium                 | Rice             |
| Corn             | White                                                         | Corn             |
| Yellow Sweet Corn| Cob                                                           | Corn             |
| Corn Cracked     | Yellow (Feed Grade)                                           | Corn             |
| Corn Grits       | Feed Grade                                                    | Corn             |
| Chicken          | Whole                                                         | Poultry          |
| Chicken Egg      | White (Pewee), White (Extra Small), White (Small), White (Medium), White (Large), White (Extra Large), White (Jumbo), Brown (Medium), Brown (Large)                   | Poultry          |
| Pork             | Belly, Ham, Frozen Liempo, Frozen Kasim                       | Livestock        |
| Beef             | Brisket, Rump                                                 | Livestock        |
| Tilapia          | null                                                          | Fish             |
| Milkfish         | null                                                          | Fish             |
| Round Scad       | null                                                          | Fish             |
| Alumahan         | null                                                          | Fish             |
| Sardines         | null                                                          | Fish             |
| Squid            | null                                                          | Fish             |
| Garlic           | null                                                          | Vegetables       |
| Ginger           | null                                                          | Vegetables       |
| Bell Pepper      | Green, Red                                                    | Vegetables       |
| Broccoli         | null                                                          | Vegetables       |
| Red Onion        | null, Medium                                                  | Vegetables       |
| White Onion      | null, Medium                                                  | Vegetables       |
| Cabbage          | Rare Ball, Scorpio, Wonder Ball                               | Vegetables       |
| Carrot           | null                                                          | Vegetables       |
| Chili            | Labuyo, Green                                                 | Vegetables       |
| Eggplant         | null                                                          | Vegetables       |
| String Beans     | null                                                          | Vegetables       |
| Baguio Beans     | null                                                          | Vegetables       |
| Squash           | null                                                          | Vegetables       |
| Tomato           | null                                                          | Vegetables       |
| Pechay Baguio    | null                                                          | Vegetables       |
| Pechay Tagalog   | null                                                          | Vegetables       |
| Chayote          | null                                                          | Vegetables       |
| Cauliflower      | null                                                          | Vegetables       |
| Celery           | null                                                          | Vegetables       |
| Mung Beans       | null                                                          | Vegetables       |
| Lettuce          | Green Ice, Iceberg, Romaine                                   | Vegetables       |
| Bittergourd      | null                                                          | Vegetables       |
| Potato           | White                                                         | Vegetables       |
| Banana           | Lakatan, Latundan, Saba                                       | Fruits           |
| Calamansi        | null                                                          | Fruits           |
| Mango            | Carabao                                                       | Fruits           |
| Avocado          | null                                                          | Fruits           |
| Melon            | null                                                          | Fruits           |
| Pomelo           | null                                                          | Fruits           |
| Watermelon       | null                                                          | Fruits           |
| Papaya           | null                                                          | Fruits           |
| Palm Oil         | 350ml, 1L                                                     | Oils             |
| Coconut Oil      | 350ml, 1L                                                     | Oils             |
| Sugar            | Brown, Refined, Washed                                        | Sugar            |

RULES:
- NEVER merge the variant into the product_name. For example, "Beef Rump" must be split: product_name="Beef", product_variant="Rump".
- NEVER put the product_name into product_variant. For example, do NOT output product_name="Pork Ham", product_variant=null. Instead: product_name="Pork", product_variant="Ham".
- Filipino/Tagalog translations (Bawang, Luya, Sibuyas, Kasim, Liempo, etc.) are NOT variants. "Kasim" = "Ham", "Liempo" = "Belly". Use the English variant name.
- If a product has both a Filipino name in parentheses AND a real variant, ignore the Filipino name and keep only the variant.
- Daily Price Index aliases: Bangus = Milkfish; Galunggong = Round Scad; Mungbean = Mung Beans; Ampalaya = Bittergourd; Chilli = Chili; Native Pechay = Pechay Tagalog; Pole Sitao = String Beans; Carrots = Carrot; White Potato = Potato.
- Keep a source specification, size, grade, cut, or brand in product_variant whenever it distinguishes separate rows. Never merge distinct rows into one series or average them together.
- Skip rows that do not map to the FOODCAST categories Rice, Corn, Poultry, Livestock, Vegetables, Fruits, Fish, Oils, or Sugar. Do not invent a category to force a match.
"""

# Use an explicit API version; preview models are not necessarily served on v1.
# Construct lazily so offline validation does not require credentials.
def _get_client():
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    return genai.Client(
        api_key=os.environ["GEMINI_API_KEY_DA_PARSER"],
        http_options=genai.types.HttpOptions(api_version="v1beta"),
    )


def parse_pdf_text_with_ai(pdf_text, report_date, source_pdf):
    """
    Send extracted Daily Price Index table text to Gemini to categorize and
    output structured JSON rows.
    """
    # Note: report_date and source_pdf are NOT requested from the AI.
    # They are injected programmatically to reduce output token usage.
    prompt = f"""
You are a data parser for Philippine Department of Agriculture Daily Price Index reports.
Extract all FOODCAST-supported commodity rows from the supplied Daily Price Index table into a JSON array.
Use only the table headed COMMODITY SPECIFICATION and PREVAILING RETAIL PRICE PER UNIT.
Each table row has one prevailing price. Copy that row's price exactly as price_index.
This report's prevailing price is already the source's mean; do not calculate another average.
Ignore table headings, category headings, explanatory notes, market rosters, and all other text.

Each item must have ONLY these fields:
- product_name: string — use a consistent English FOODCAST name
- product_category: string (one of {', '.join(CATEGORY_LIST)})
- product_variant: string or null — preserve each distinguishing source specification
- unit: string (kg, piece, liter, etc.), following the report's unit notes
- origin: string ('Local' or 'Imported'); use row or section context, default to 'Local' only when not specified
- price_index: positive number printed in that exact commodity row

Read each commodity, specification, origin, and price as one row, even when PDF text wraps onto multiple lines. Never attach a nearby price to a product when alignment is unclear. Skip rows marked n/a or with no numeric price; never turn them into zero. Do not combine brands, sizes, origins, or different cuts into a synthetic average.
The unit notes state that agri-fishery items except eggs are P/kg, eggs are P/piece, salt and sugar are P/kg, and cooking oil is P/liter. Use the corresponding unit for each supported item.

Do NOT include report_date or source_pdf fields, I will add those myself.

{PRODUCT_VARIANT_REF}

PDF text to parse:
{pdf_text}

Return ONLY a valid JSON array. No extra text or explanation.
"""

    # Bounded backoff gives Gemini a chance to recover from transient 503s.
    MAX_RETRIES = 3
    RETRY_DELAYS_SECONDS = (2, 5)
    data = []
    client = _get_client()
    model = os.environ.get("GEMINI_MODEL_DA_PARSER", "gemini-2.5-flash").strip()
    if not model:
        raise RuntimeError("GEMINI_MODEL_DA_PARSER must not be empty")

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=32768,
                    response_mime_type="application/json"
                )
            )

            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = getattr(candidates[0], "finish_reason", None)
                finish_name = getattr(finish_reason, "name", str(finish_reason)).upper()
                if "MAX_TOKENS" in finish_name:
                    raise ValueError("Gemini stopped at the output-token limit")

            raw = (response.text or "").strip()
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("Gemini returned JSON that was not an array")
            break

        except json.JSONDecodeError as e:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES}: incomplete or invalid JSON ({e}).")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS_SECONDS[attempt])
            else:
                raise RuntimeError("DA parser returned invalid JSON after retries") from e

        except Exception as e:
            code = getattr(e, "code", None)
            if str(code) in {"400", "401", "403", "404"}:
                raise RuntimeError(
                    f"DA Gemini configuration failure (HTTP {code}, model={model}, "
                    "API=v1beta). Check GEMINI_MODEL_DA_PARSER and model access; "
                    "no price rows were written."
                ) from e
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES}: Gemini API error: {e}")
            if attempt >= MAX_RETRIES - 1:
                raise RuntimeError("DA Gemini extraction failed after retries") from e
            time.sleep(RETRY_DELAYS_SECONDS[attempt])

    # The Daily Price Index has no low/high columns. Reject rows that look like
    # they were interpreted using the different Retail Price Range report.
    validated = []
    rejected = []
    seen_identities = set()
    rows_to_check = data if isinstance(data, list) else []
    for row in rows_to_check:
        if not isinstance(row, dict):
            rejected.append("row is not an object")
            continue

        product_name = row.get("product_name")
        product_category = row.get("product_category")
        unit = row.get("unit")
        origin = row.get("origin") or "Local"
        variant = row.get("product_variant")
        if not isinstance(product_name, str) or not product_name.strip():
            rejected.append("missing product name")
            continue
        if not isinstance(product_category, str):
            rejected.append(f"{product_name}: missing product category")
            continue
        category = next((item for item in CATEGORY_LIST
                         if item.casefold() == product_category.strip().casefold()), None)
        if category is None:
            rejected.append(f"{product_name}: unsupported category {product_category!r}")
            continue
        if not isinstance(unit, str) or not unit.strip():
            rejected.append(f"{product_name}: missing unit")
            continue
        if not isinstance(origin, str) or origin.strip().casefold() not in {"local", "imported"}:
            rejected.append(f"{product_name}: unsupported origin {origin!r}")
            continue
        if variant is not None and not isinstance(variant, str):
            rejected.append(f"{product_name}: invalid product variant")
            continue
        if "reported_low" in row or "reported_high" in row:
            rejected.append(f"{product_name}: unexpected retail-range bounds in a price-index row")
            continue

        try:
            price = float(row.get("price_index"))
        except (TypeError, ValueError):
            rejected.append(f"{product_name}: unparseable price")
            continue
        if not math.isfinite(price) or price <= 0:
            rejected.append(f"{product_name}: non-positive price")
            continue

        normalized_origin = "Imported" if origin.strip().casefold() == "imported" else "Local"
        normalized_variant = variant.strip() if variant and variant.strip() else "Standard"
        identity = (product_name.strip().casefold(), normalized_variant.casefold(),
                    normalized_origin.casefold())
        if identity in seen_identities:
            rejected.append(
                f"{product_name}: duplicate commodity identity; preserve its distinct specification as a variant"
            )
            continue
        seen_identities.add(identity)

        row["price_index"] = price
        row["product_name"] = product_name.strip()
        row["product_category"] = category
        row["product_variant"] = variant.strip() if variant and variant.strip() else None
        row["unit"] = unit.strip()
        row["origin"] = normalized_origin
        row["report_date"] = str(report_date)
        row["source_pdf"] = source_pdf
        validated.append(row)

    if rejected:
        print(f"Quarantined {len(rejected)} invalid DA price row(s): " + "; ".join(rejected[:8]))
        print("Rejecting this PDF parse to prevent a partial upsert; it can be retried after parser review.")
        return []
    return validated
