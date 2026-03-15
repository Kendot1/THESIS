import requests

API_URL = "https://www.da.gov.ph/wp-json/wp/v2/media?per_page=100"

def get_pdf_links():

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(API_URL, headers=headers)

    print("Status:", response.status_code)

    data = response.json()

    pdf_links = []

    for item in data:

        file_url = item.get("source_url")

        if file_url and file_url.endswith(".pdf"):
            pdf_links.append(file_url)

    return pdf_links