import requests
from datetime import datetime, timedelta
 
BASE_URL = "https://www.da.gov.ph/wp-content/uploads"
 
def get_pdf_links(start_date, end_date):
    pdf_links = []
    current = start_date
 
    while current <= end_date:
        year = current.year
        month_name = current.strftime("%B")
        day = current.day
 
        # Try both zero-padded (19) and non-padded (19) day formats
        # DA website has been inconsistent across years
        day_formats = [
            str(day),          # e.g. 19  (no padding — common in 2026)
            f"{day:02d}",      # e.g. 19  (zero-padded — common in 2025)
        ]
 
        # Try current month folder, previous month folder, and next month folder
        prev_month = (current.replace(day=1) - timedelta(days=1)).strftime("%m")
        curr_month = current.strftime("%m")
        next_month = (current.replace(day=1) + timedelta(days=32)).strftime("%m")
        candidate_months = [curr_month, next_month, prev_month]
 
        found = False
        tried_urls = []
 
        for day_str in day_formats:
            if found:
                break
            filename = f"Price-Monitoring-{month_name}-{day_str}-{year}.pdf"
            for month_folder in candidate_months:
                url = f"{BASE_URL}/{year}/{month_folder}/{filename}"
                tried_urls.append(url)
                try:
                    response = requests.head(url, timeout=5)
                    if response.status_code == 200:
                        pdf_links.append(url)
                        print(f"✅ Found: {url}")
                        found = True
                        break
                except Exception as e:
                    print(f"  ⚠️  Network error checking {url}: {e}")
                    break  # No point trying more URLs if network is down
 
        if not found:
            print(f"⚠️  No PDF found for {month_name} {day}, {year}")
            print(f"    Tried: {tried_urls[0]}")
            print(f"           {tried_urls[1] if len(tried_urls) > 1 else ''}")
 
        current += timedelta(days=1)
 
    return pdf_links
 