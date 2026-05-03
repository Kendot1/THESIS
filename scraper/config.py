import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

REPORT_PAGE = "https://www.da.gov.ph/price-monitoring/"

DOWNLOAD_FILE = "report.pdf"
OUTPUT_FILE = "price_report.xlsx"