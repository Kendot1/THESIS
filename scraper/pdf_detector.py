import time
from datetime import timedelta

import requests


BASE_URL = "https://www.da.gov.ph/wp-content/uploads"
USER_AGENT = "FOODCAST-DA-price-monitor/1.0 (+https://www.da.gov.ph/)"


def _check_pdf(url):
    """Return True/False for a reachable URL, or None after transient failures."""
    headers = {"User-Agent": USER_AGENT}
    last_error = None
    for attempt in range(3):
        try:
            response = requests.head(
                url, headers=headers, timeout=(5, 12), allow_redirects=True
            )
            if response.status_code in (403, 405):
                # Some WordPress/CDN configurations reject HEAD but allow GET.
                response.close()
                response = requests.get(
                    url,
                    headers={**headers, "Range": "bytes=0-0"},
                    timeout=(5, 12),
                    allow_redirects=True,
                    stream=True,
                )
            status = response.status_code
            response.close()
            if status in (200, 206):
                return True
            if status == 404:
                return False
            if status < 500 and status != 429:
                return None
            last_error = f"HTTP {status}"
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    print(f"Unable to check DA PDF URL after retries: {url}: {last_error}")
    return None


def get_pdf_links(start_date, end_date):
    pdf_links = []
    current = start_date

    while current <= end_date:
        year = current.year
        month_name = current.strftime("%B")
        day = current.day
        day_formats = dict.fromkeys((str(day), f"{day:02d}"))
        prev_month = (current.replace(day=1) - timedelta(days=1)).strftime("%m")
        next_month = (current.replace(day=1) + timedelta(days=32)).strftime("%m")
        month_folders = dict.fromkeys((current.strftime("%m"), next_month, prev_month))
        found = False
        uncertain = False

        for day_text in day_formats:
            filename = f"Price-Monitoring-{month_name}-{day_text}-{year}.pdf"
            for month_folder in month_folders:
                url = f"{BASE_URL}/{year}/{month_folder}/{filename}"
                exists = _check_pdf(url)
                if exists is True:
                    pdf_links.append(url)
                    print(f"Found DA report: {url}")
                    found = True
                    break
                if exists is None:
                    uncertain = True
            if found:
                break

        # A report may be absent on weekends/holidays. If every candidate path
        # failed transiently, fail the job so a network outage cannot look like
        # a successful empty scrape.
        if not found and uncertain:
            raise RuntimeError(
                "DA PDF discovery could not verify "
                f"{current:%Y-%m-%d}; check DA availability and runner network access"
            )
        current += timedelta(days=1)

    return pdf_links
