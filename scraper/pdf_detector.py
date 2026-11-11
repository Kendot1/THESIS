"""Discover DA daily price reports from the official price-monitoring page."""
from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from .utils import extract_date_from_url
except ImportError:  # Script execution from the scraper directory.
    from utils import extract_date_from_url


DA_PRICE_MONITORING_PAGE = "https://www.da.gov.ph/price-monitoring/"
USER_AGENT = "FOODCAST-DA-price-monitor/1.0 (+https://www.da.gov.ph/)"
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_INDEX_HEADING = re.compile(r"^\d{4}\s+Daily\s+Price\s+Index$", re.IGNORECASE)


def extract_daily_index_links(
    html: str, start_date: date, end_date: date
) -> list[str]:
    """Return dated PDF links from the Daily Price Index section only."""
    if end_date < start_date:
        raise ValueError("end date must be on or after start date")

    soup = BeautifulSoup(html, "html.parser")
    target_heading = None
    target_text = f"{end_date.year} Daily Price Index"
    for heading in soup.find_all(sorted(_HEADING_TAGS)):
        text = " ".join(heading.get_text(" ", strip=True).split())
        if text.casefold() == target_text.casefold() and _INDEX_HEADING.fullmatch(text):
            target_heading = heading
            break
    if target_heading is None:
        raise RuntimeError(f"DA page is missing the {target_text!r} section")

    links_by_date = {}
    for element in target_heading.find_all_next():
        if element.name in _HEADING_TAGS:
            break
        if element.name != "a":
            continue
        href = element.get("href")
        if not href:
            continue
        url = urljoin(DA_PRICE_MONITORING_PAGE, href)
        parsed_url = urlparse(url)
        if (parsed_url.hostname not in {"www.da.gov.ph", "da.gov.ph"}
                or "/wp-content/uploads/" not in parsed_url.path.lower()
                or not parsed_url.path.lower().endswith(".pdf")):
            continue
        try:
            report_date = extract_date_from_url(url)
        except ValueError:
            continue
        if report_date is None or not start_date <= report_date <= end_date:
            continue
        # Keep the first official listing for a date; the page's order is newest
        # report first and may point to a revised PDF filename.
        links_by_date.setdefault(report_date, url)

    return [links_by_date[day] for day in sorted(links_by_date)]


def fetch_official(url):
    """Bounded HTTPS fetch; only the two official DA host spellings allowed."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.da.gov.ph', 'da.gov.ph'}:
        raise ValueError(f'Not an official DA HTTPS URL: {url}')
    alternate = parsed._replace(netloc='da.gov.ph' if parsed.hostname == 'www.da.gov.ph' else 'www.da.gov.ph').geturl()
    errors = []
    for candidate in (url, alternate):
        try:
            response = requests.get(candidate, headers={'User-Agent': USER_AGENT}, timeout=(20, 45))
            response.raise_for_status()
            final = urlparse(getattr(response, 'url', candidate))
            if final.scheme != 'https' or final.hostname not in {'www.da.gov.ph', 'da.gov.ph'}:
                raise RuntimeError('DA source redirected outside official HTTPS hosts')
            return response
        except requests.RequestException as exc:
            errors.append(f'{candidate}: {exc}')
    raise RuntimeError('Official DA sources unavailable: ' + '; '.join(errors))


def get_pdf_links(start_date: date, end_date: date) -> list[str]:
    """Fetch official DA listing and return available daily price index PDFs.

    Missing dates remain missing. The caller must not fill them with copied
    prices; each returned link's filename carries its own report date.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    response = fetch_official(DA_PRICE_MONITORING_PAGE)
    links = extract_daily_index_links(response.text, start_date, end_date)
    print(
        f"Found {len(links)} DA Daily Price Index PDF(s) listed for "
        f"{start_date.isoformat()} through {end_date.isoformat()}."
    )
    return links
