import pdfplumber
import statistics

def parse_pdf(file, source):

    rows = []

    with pdfplumber.open(file) as pdf:

        for page in pdf.pages:

            table = page.extract_table()

            if table:

                prices = []

                product_name = table[0][0]
                product_type = table[0][1]

                for row in table[1:]:

                    price = row[1]

                    if price and price != "N/A":

                        if "-" in price:

                            p1, p2 = price.split("-")
                            price = (float(p1) + float(p2)) / 2

                        prices.append(float(price))

                if prices:

                    price_index = statistics.mean(prices)

                    rows.append({
                        "product_name": product_name,
                        "product_type": product_type,
                        "price_index": price_index,
                        "source_pdf": source
                    })

    return rows