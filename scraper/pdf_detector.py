import requests
from bs4 import BeautifulSoup

URL = "https://www.da.gov.ph/price-monitoring/"

def get_pdf_links():

    response = requests.get(URL)
    soup = BeautifulSoup(response.text, "html.parser")

    pdf_links = []

    for link in soup.find_all("a"):

        href = link.get("href")

        if href and "Daily-Retail-Price-Range" in href and href.endswith(".pdf"):

            if href.startswith("/"):
                href = "https://www.da.gov.ph" + href

            pdf_links.append(href)

    return pdf_links