import os
import json
from google import genai

CATEGORY_LIST = ["Rice", "Corn", "Poultry", "Livestock", "Vegetables",
                 "Fruits", "Fish", "Oils", "Sugar"]

# Initialize Gemini client
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def parse_pdf_text_with_ai(pdf_text, report_date, source_pdf):
    """
    Send extracted yellow table text to Gemini to clean, categorize,
    and output structured JSON rows.
    """
    prompt = f"""
You are a data parser for agricultural commodity price reports. 
Extract all products from the following PDF text into a JSON array. 
Only include the yellow average price table. Ignore other formats.

Each item must have the fields exactly as below:
- product_name: string (e.g., 'Chicken Egg')
- product_category: string (one of {', '.join(CATEGORY_LIST)})
- product_variant: string or null (e.g., 'White, Pewee')
- unit: string (kg, piece, liter, etc.)
- origin: string ('Local' or 'Imported', default to 'Local' if unspecified)
- price_index: number (average price)
- report_date: string (YYYY-MM-DD, use {report_date})
- source_pdf: string (use {source_pdf})

PDF text to parse:
{pdf_text}

Return ONLY valid JSON array, ready for insertion into the database. 
Do not include any extra text or explanation.
"""

    # Call Gemini
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt
    )

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        print("Failed to parse Gemini output as JSON:", e)
        data = []

    return data