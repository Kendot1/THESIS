import os
import json
import re
from google import genai

CATEGORY_LIST = ["Rice", "Corn", "Poultry", "Livestock", "Vegetables",
                 "Fruits", "Fish", "Oils", "Sugar"]

# Canonical product name → variant mapping for consistency across all dates
PRODUCT_VARIANT_REF = """
CANONICAL PRODUCT REFERENCE (you MUST follow this exact naming):
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
- If a product is not in this reference table, use your best judgment but follow the same pattern: broad product_name + specific product_variant.
"""

# Initialize Gemini client
client = genai.Client(api_key=os.environ["GEMINI_API_KEY_DA_PARSER"])


def _repair_truncated_json(raw: str) -> list:
    """
    Attempt to repair truncated JSON arrays by closing open structures.
    Returns parsed list or empty list on failure.
    """
    raw = raw.strip()

    # Remove any trailing incomplete object (after the last complete '}')
    last_close = raw.rfind("}")
    if last_close == -1:
        return []

    raw = raw[:last_close + 1]

    # Close the array if it's not closed
    if not raw.rstrip().endswith("]"):
        # Remove any trailing comma after the last object
        raw = raw.rstrip().rstrip(",")
        raw += "\n]"

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def parse_pdf_text_with_ai(pdf_text, report_date, source_pdf):
    """
    Send extracted yellow table text to Gemini to clean, categorize,
    and output structured JSON rows.
    """
    # Note: report_date and source_pdf are NOT requested from the AI.
    # They are injected programmatically to reduce output token usage.
    prompt = f"""
You are a data parser for Philippine DA agricultural commodity price reports.
Extract all products from the following PDF text into a JSON array.
Only include the yellow average price table. Ignore other formats.

Each item must have ONLY these fields:
- product_name: string — use the ENGLISH name only, must match the canonical reference below
- product_category: string (one of {', '.join(CATEGORY_LIST)})
- product_variant: string or null — the specific cut, type, size, grade, or breed. Must match canonical reference below.
- unit: string (kg, piece, liter, etc.)
- origin: string ('Local' or 'Imported', default to 'Local' if unspecified)
- price_index: number (average price)

Do NOT include report_date or source_pdf fields, I will add those myself.

{PRODUCT_VARIANT_REF}

PDF text to parse:
{pdf_text}

Return ONLY a valid JSON array. No extra text or explanation.
"""

    MAX_RETRIES = 2
    data = []

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=32768,
                    response_mime_type="application/json"
                )
            )

            raw = response.text.strip()
            data = json.loads(raw)
            break  # Success — exit retry loop

        except json.JSONDecodeError as e:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES}: JSON parse error ({e}). Trying truncation repair...")
            repaired = _repair_truncated_json(raw)
            if repaired:
                print(f"  Repair recovered {len(repaired)} rows from truncated output.")
                data = repaired
                break
            elif attempt < MAX_RETRIES - 1:
                print(f"  Repair failed. Retrying...")
            else:
                print(f"  All {MAX_RETRIES} attempts failed. Skipping this PDF.")
                print(f"  RAW OUTPUT (last 200 chars): ...{raw[-200:]}")

        except Exception as e:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES}: Gemini API error: {e}")
            if attempt >= MAX_RETRIES - 1:
                print(f"  All {MAX_RETRIES} attempts failed. Skipping this PDF.")

    # Inject report_date and source_pdf into each row
    for row in data:
        row["report_date"] = str(report_date)
        row["source_pdf"] = source_pdf

    return data