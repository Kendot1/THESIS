import requests
from datetime import datetime, timedelta

BASE_URL = "https://www.da.gov.ph/wp-content/uploads"

def get_pdf_links(start_date=datetime(2020, 1, 1)):
    pdf_links = []
    end_date = datetime(2020, 12, 31)
    current = start_date

    while current <= end_date:
        year = current.year
        month = current.strftime("%m")
        month_name = current.strftime("%B")
        day = current.day
        filename = f"Price-Monitoring-{month_name}-{day}-{year}.pdf"
        url = f"{BASE_URL}/{year}/{month}/{filename}"


        try:
            response = requests.head(url, timeout=5)
            if response.status_code == 200:
                pdf_links.append(url)
        except:
            pass

        current += timedelta(days=1)

    return pdf_links