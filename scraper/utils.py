import re
from datetime import datetime

def extract_date_from_url(url):

    match = re.search(r'([A-Za-z]+)-(\d+)-(\d+)', url)

    if match:

        month, day, year = match.groups()

        date = datetime.strptime(f"{month} {day} {year}", "%B %d %Y")

        return date.date()

    return None