from pdf_detector import get_pdf_links
from parser import parse_pdf
from db import insert_prices

def run():
    pdf_links = get_pdf_links()
    print(f"PDF links found: {len(pdf_links)}")

    for link in pdf_links:
        print("Processing:", link)
        try:
            rows = parse_pdf(link)
            insert_prices(rows)
            print(f"Inserted {len(rows)} rows from {link}")
        except Exception as e:
            print(f"Failed to process {link}: {e}")

if __name__ == "__main__":
    run()