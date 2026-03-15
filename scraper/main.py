from pdf_detector import get_pdf_links
from downloader import download_pdf
from parser import parse_pdf
from db import insert_prices

def run():

    pdf_links = get_pdf_links()

    print("PDF links found:", len(pdf_links))

    for link in pdf_links:

        print("Processing:", link)

        file = download_pdf(link)

        rows = parse_pdf(file, link)

        print("Rows extracted:", len(rows))

        insert_prices(rows)

if __name__ == "__main__":
    run()