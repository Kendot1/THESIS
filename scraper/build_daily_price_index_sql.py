"""Build a local, read-only DA Daily Price Index replacement artifact.

This script never connects to Supabase. It downloads the official DA PDFs,
extracts table cells, preserves a raw extraction snapshot, maps supported rows
to FOODCAST series, and writes a date-bounded SQL file for human review.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
DA_INDEX_URL = "https://www.da.gov.ph/price-monitoring/"
START_DATE = date(2025, 3, 1)
LATEST_COVERED_DATE = date(2026, 10, 23)
OUTPUT_DIR = ROOT / "audits" / "daily_price_index_rebuild_20261024"
SOURCE_PDF_DIR = OUTPUT_DIR / "source_pdfs"
ARCHIVE_LINK_SNAPSHOT = OUTPUT_DIR / "official_archive_links.json"
FOODCAST_NAMES_REFERENCE = ROOT / "audits" / "accuracy_goal_20261011" / "supabase_food_prices_through_20261005.json"
RESUMABLE_TITLE_GATE_CODE_SHA256 = "6617e82db767ed8bd5f01d596191a4cc2b672e730ec874c659fca341cb3cbc8b"
RESUMABLE_COMPLETE_PARSE_CODE_SHA256 = "0b78511703624239b62a4c1444492e8a83d288bb11426474701884b2a807a431"
# These two cached reports used table-section layouts repaired after the saved
# complete parse. Refresh them from their immutable local PDFs during resume.
LAYOUT_REFRESH_LINK_LABEL_DATES = {"2025-04-09", "2025-09-25"}
MONTHS = {
    name.casefold(): number
    for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"), 1)
}
DATE_RE = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b")
DAY_MONTH_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\b")
PRICE_RE = re.compile(r"^(?:\d[\d,]*(?:\.\d+)?|n\s*/\s*a(?:s)?|#?\s*div\s*/\s*0!?|#?div0!?)$", re.I)
ORIGIN_RE = re.compile(r"\b(local|imported)\b", re.I)
SPACE_RE = re.compile(r"\s+")
SECTION_HEADINGS = {
    "IMPORTED COMMERCIAL RICE", "LOCAL COMMERCIAL RICE", "CORN", "CORN PRODUCTS",
    "LEGUMES", "FISH", "FISH PRODUCTS", "LIVESTOCK & POULTRY", "PRODUCTS",
    "LOWLAND VEGETABLES", "HIGHLAND VEGETABLES", "SPICES", "FRUITS",
    "OTHER BASIC COMMODITIES", "BEEF MEAT PRODUCTS", "PORK MEAT PRODUCTS",
    "OTHER LIVESTOCK MEAT PRODUCTS", "POULTRY PRODUCTS",
}
FISH_SOURCE_PREFIXES = (
    "galunggong", "bangus", "alumahan", "tilapia", "indian mackerel", "mackerel",
    "sardines", "squid", "tambakol", "yellow-fin tuna", "salmon belly", "salmon head",
    "tanigue", "ssstanigue", "pampano", "pompano", "bonito",
)
VEGETABLE_SOURCE_PREFIXES = (
    "eggplant", "native pechay", "pechay", "pole sitao", "sitao", "ampalaya",
    "bittergourd", "chilli", "chili", "tiger chillies", "squash", "tomato",
    "bell pepper", "broccoli", "cauliflower", "cabbage", "carrots", "carrot",
    "celery", "chayote", "habichuelas", "baguio beans", "lettuce", "white potato",
    "potato", "garlic", "ginger", "red onion", "white onion", "mungbean", "mung bean",
)
FRUIT_SOURCE_PREFIXES = (
    "banana", "calamansi", "mango", "avocado", "melon", "papaya", "pomelo", "watermelon",
)
FOODCAST_PRODUCT_NAMES = frozenset({
    ("Corn", "Corn"), ("Corn", "Corn Cracked"), ("Corn", "Corn Grits"),
    ("Corn", "Yellow Sweet Corn"),
    ("Fish", "Bonito"), ("Fish", "Indian Mackerel"), ("Fish", "Milkfish"),
    ("Fish", "Round Scad"), ("Fish", "Salmon Head"), ("Fish", "Sardines"),
    ("Fish", "Squid"), ("Fish", "Tilapia"), ("Fish", "Yellow-Fin Tuna"),
    ("Fruits", "Avocado"), ("Fruits", "Banana"), ("Fruits", "Calamansi"),
    ("Fruits", "Mango"), ("Fruits", "Melon"), ("Fruits", "Papaya"),
    ("Fruits", "Pomelo"), ("Fruits", "Watermelon"),
    ("Livestock", "Beef"), ("Livestock", "Pork"),
    ("Oils", "Coconut Oil"), ("Oils", "Palm Oil"),
    ("Poultry", "Chicken"), ("Poultry", "Chicken Egg"),
    ("Rice", "Rice"), ("Sugar", "Sugar"),
    ("Vegetables", "Baguio Beans"), ("Vegetables", "Bell Pepper"),
    ("Vegetables", "Bittergourd"), ("Vegetables", "Broccoli"),
    ("Vegetables", "Cabbage"), ("Vegetables", "Carrot"),
    ("Vegetables", "Cauliflower"), ("Vegetables", "Celery"),
    ("Vegetables", "Chayote"), ("Vegetables", "Chili"),
    ("Vegetables", "Eggplant"), ("Vegetables", "Garlic"),
    ("Vegetables", "Ginger"), ("Vegetables", "Lettuce"),
    ("Vegetables", "Mung Beans"), ("Vegetables", "Pechay Baguio"),
    ("Vegetables", "Pechay Tagalog"), ("Vegetables", "Potato"),
    ("Vegetables", "Red Onion"), ("Vegetables", "Squash"),
    ("Vegetables", "String Beans"), ("Vegetables", "Tomato"),
    ("Vegetables", "White Onion"),
})


def _clean(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "").replace("\xa0", " ")).strip()


def _date_from_text(text: str) -> date | None:
    match = DATE_RE.search(text)
    if match:
        month, day, year = match.groups()
        month_number = MONTHS.get(month.casefold())
        if month_number is not None:
            try:
                return date(int(year), month_number, int(day))
            except ValueError:
                pass
    match = DAY_MONTH_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    month_number = MONTHS.get(month.casefold())
    if month_number is None:
        return None
    try:
        return date(int(year), month_number, int(day))
    except ValueError:
        return None


def _embedded_report_date(text: str) -> date:
    monitoring = re.search(r"Date\s+of\s+Monitoring\s*:\s*(.+)", text, re.I)
    if monitoring:
        parsed = _date_from_text(monitoring.group(1))
        if parsed is not None:
            return parsed
    dates = set()
    for pattern in (DATE_RE, DAY_MONTH_DATE_RE):
        for match in pattern.finditer(text):
            parsed = _date_from_text(match.group(0))
            if parsed is not None:
                dates.add(parsed)
    if len(dates) != 1:
        raise RuntimeError(f"Could not identify one unambiguous report date in PDF title: {sorted(dates)}")
    return next(iter(dates))


def _resolve_report_date(text: str, link_label_date: date) -> tuple[date, date, str | None]:
    printed_date = _embedded_report_date(text)
    if printed_date == link_label_date:
        return printed_date, printed_date, None
    monitoring = re.search(r"Date\s+of\s+Monitoring\s*:\s*(.+)", text, re.I)
    weekday = re.search(
        r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        monitoring.group(1) if monitoring else text[:600], re.I,
    )
    if (weekday and (link_label_date - printed_date).days == 1
            and weekday.group(1).casefold() == link_label_date.strftime("%A").casefold()
            and weekday.group(1).casefold() != printed_date.strftime("%A").casefold()):
        return printed_date, link_label_date, (
            "The DA link label and printed weekday agree on the report date; "
            "the printed day-of-month conflicts with both. Original printed date retained."
        )
    return printed_date, printed_date, None


def _source_upload_month(source_pdf: str) -> str | None:
    match = re.search(r"/uploads/(\d{4})/(\d{2})/", urlparse(source_pdf).path, re.I)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _report_date_in_text(text: str, expected: date) -> bool:
    normalized = _clean(text)
    month_first = re.search(
        rf"\b{expected.strftime('%B')}\s+0?{expected.day},?\s+{expected.year}\b",
        normalized, re.I,
    )
    day_first = re.search(
        rf"\b0?{expected.day}\s+{expected.strftime('%B')},?\s+{expected.year}\b",
        normalized, re.I,
    )
    return bool(month_first or day_first)


def _curl(url: str) -> bytes:
    result = subprocess.run(
        ["curl.exe", "--noproxy", "*", "--fail", "--silent", "--show-error",
         "--location", "--connect-timeout", "15", "--max-time", "60",
         "--retry", "3", "--retry-delay", "2", url],
        check=True, capture_output=True, timeout=75,
    )
    if not result.stdout:
        raise RuntimeError(f"Empty response from {url}")
    return result.stdout


def discover_pdfs() -> tuple[list[tuple[date, str]], str, str]:
    try:
        html = _curl(DA_INDEX_URL)
    except Exception as exc:
        if not ARCHIVE_LINK_SNAPSHOT.exists():
            raise
        snapshot_bytes = ARCHIVE_LINK_SNAPSHOT.read_bytes()
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        if snapshot.get("source_listing") != DA_INDEX_URL:
            raise RuntimeError("Cached archive link snapshot has an unexpected source") from exc
        links = []
        for item in snapshot.get("links", []):
            link_label_date = date.fromisoformat(item.get("link_label_date", item.get("listing_date")))
            url = item["url"]
            parsed = urlparse(url)
            if (parsed.hostname not in {"www.da.gov.ph", "da.gov.ph"}
                    or "/wp-content/uploads/" not in parsed.path.lower()
                    or not parsed.path.lower().endswith(".pdf")
                    or not START_DATE <= link_label_date <= LATEST_COVERED_DATE):
                raise RuntimeError(f"Untrusted or out-of-range archive link snapshot entry: {item}") from exc
            links.append((link_label_date, url))
        links.sort()
        if (len(links) != snapshot.get("link_count")
                or len({d for d, _ in links}) != len(links)
                or not links or links[0][0] != START_DATE
                or links[-1][0] != LATEST_COVERED_DATE):
            raise RuntimeError("Cached archive link snapshot failed completeness checks") from exc
        return links, "verified_official_link_snapshot_after_network_failure", sha256(snapshot_bytes).hexdigest()
    soup = BeautifulSoup(html, "html.parser")
    active_year: int | None = None
    found: list[tuple[date, str]] = []
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    for element in soup.find_all([*heading_tags, "a"]):
        text = _clean(element.get_text(" ", strip=True))
        if element.name in heading_tags:
            match = re.fullmatch(r"(2025|2026) Daily Price Index", text, re.I)
            active_year = int(match.group(1)) if match else None
            continue
        if active_year is None:
            continue
        href = element.get("href")
        if not href:
            continue
        url = urljoin(DA_INDEX_URL, href)
        parsed = urlparse(url)
        if (parsed.hostname not in {"www.da.gov.ph", "da.gov.ph"}
                or "/wp-content/uploads/" not in parsed.path.lower()
                or not parsed.path.lower().endswith(".pdf")):
            continue
        report_date = _date_from_text(text) or _date_from_text(parsed.path.replace("-", " "))
        if report_date is None or report_date.year != active_year:
            raise RuntimeError(f"Cannot safely identify report date for {url}")
        if START_DATE <= report_date <= LATEST_COVERED_DATE:
            found.append((report_date, url))

    by_date: dict[date, str] = {}
    for report_date, url in found:
        if report_date in by_date and by_date[report_date] != url:
            raise RuntimeError(f"Multiple official DPI PDFs listed for {report_date}")
        by_date[report_date] = url
    if not by_date:
        raise RuntimeError("No Daily Price Index PDFs were found in the cutover range")
    return sorted(by_date.items()), "live_official_archive_page", sha256(html).hexdigest()


def _joined(cells: list[Any]) -> str:
    parts = [_clean(cell) for cell in cells if _clean(cell)]
    return _clean(" ".join(parts))


def _row_groups(row: list[Any]) -> tuple[str, str, str, str]:
    if len(row) >= 12:
        groups = (
            _joined(row[0:3]), _joined(row[3:6]),
            _joined(row[6:9]), _joined(row[9:12]),
        )
        if not groups[0] and groups[1].upper() in SECTION_HEADINGS:
            return groups[1], "", "", ""
        if groups[0].isdigit():
            return groups[1], groups[2], "", groups[3]
        if len(groups[0]) == 1 and groups[0].isalpha() and groups[1]:
            return groups[1], "", "", ""
        return groups
    if len(row) >= 9:
        return _joined(row[0:3]), _joined(row[3:6]), "", _joined(row[6:9])
    if len(row) == 7:
        first, second, price = _joined(row[0:3]), _joined(row[3:6]), _clean(row[6])
        if len(first) == 1 and first.isalpha() and second:
            return second, "", "", ""
        if not first and second.upper() in SECTION_HEADINGS:
            return second, "", "", ""
        return first, second, "", price
    if len(row) == 6 and _clean(row[0]).isdigit():
        # A newer 2025 annex layout uses ordinal, commodity, two spacer cells,
        # specification, and price.
        return _clean(row[1]), _clean(row[4]), "", _clean(row[5])
    if len(row) == 6 and len(_clean(row[0])) == 1 and _clean(row[0]).isalpha():
        heading = _joined(row[1:])
        return heading, "", "", ""
    # Newer DA PDFs use three cells: commodity, specification, price.
    # Older PDFs have four logical cells (or 12 physical subcells above).
    if len(row) == 3:
        return _clean(row[0]), _clean(row[1]), "", _clean(row[2])
    if len(row) == 4 and (_clean(row[0]).isdigit() or _clean(row[0]).casefold() in {"n/a", "na"}):
        # Some 2025 table revisions prepend an ordinal row number; a few
        # reports have a corrupted ordinal cell containing n/a.
        return _clean(row[1]), _clean(row[2]), "", _clean(row[3])
    if (len(row) == 4 and len(_clean(row[0])) == 1
            and _clean(row[0]).isalpha() and _clean(row[1])
            and not _clean(row[2]) and not _clean(row[3])):
        # Lettered section headings in the numbered 2025 annex layout.
        return _clean(row[1]), "", "", ""
    values = [_clean(cell) for cell in row]
    values += [""] * (4 - len(values))
    return values[0], values[1], values[2], values[3]


def _is_table_header(row: list[Any]) -> bool:
    joined = " ".join(_clean(cell).casefold() for cell in row if _clean(cell))
    return ("commodity" in joined or "specification" in joined) and "price" in joined


def _is_repeated_header_fragment(row: list[Any]) -> bool:
    cells = {_clean(cell).casefold() for cell in row if _clean(cell)}
    return bool(cells) and cells <= {
        "prevailing", "prevailing retail", "retail price", "retail price per",
        "retail price per unit (p/unit)",
        "price per unit", "unit (p/unit)", "(p/unit)", "p/unit",
        "commodity", "specification",
    }


def _extract_table_rows(pdf_bytes: bytes, listing_date: date, source_pdf: str) -> tuple[list[dict], dict]:
    raw_rows: list[dict] = []
    page_text: list[str] = []
    sections_seen: set[str] = set()
    table_headers = 0
    current_section = ""

    with pdfplumber.open(__import__("io").BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            raise RuntimeError(f"PDF has no pages: {source_pdf}")
        for page_number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise RuntimeError(f"Page {page_number} has no extractable text: {source_pdf}")
            page_text.append(text)
            for table in page.extract_tables() or []:
                has_header = any(_is_table_header(row) for row in table if row)
                if has_header:
                    table_headers += 1
                elif table_headers == 0:
                    continue

                for row_number, row in enumerate(table, 1):
                    if not row or _is_table_header(row) or _is_repeated_header_fragment(row):
                        continue
                    commodity, specification, explicit_unit, raw_price = _row_groups(row)
                    if not any((commodity, specification, explicit_unit, raw_price)):
                        continue

                    folded_price = raw_price.casefold().replace(" ", "")
                    if not raw_price and commodity and not specification and not explicit_unit:
                        heading = commodity.upper()
                        if heading in {"IMPORTED COMMERCIAL", "LOCAL COMMERCIAL"}:
                            current_section = heading
                            continue
                        if heading == "RICE" and current_section in {"IMPORTED COMMERCIAL", "LOCAL COMMERCIAL"}:
                            current_section = f"{current_section} RICE"
                            sections_seen.add(current_section)
                            continue
                        if heading in SECTION_HEADINGS:
                            current_section = heading
                            sections_seen.add(current_section)
                            continue
                    if not PRICE_RE.fullmatch(folded_price):
                        continue
                    na_markers = {"n/a", "na", "n/as", "n/a/s"}
                    calculation_error_markers = {"#div/0!", "div/0!", "#div/0", "div/0"}
                    available = folded_price not in na_markers | calculation_error_markers
                    price = None
                    availability_reason = (
                        "source_not_available_marker" if folded_price in na_markers else
                        "source_calculation_error_omitted" if folded_price in calculation_error_markers else
                        None
                    )
                    if available:
                        try:
                            price = Decimal(folded_price.replace(",", ""))
                        except InvalidOperation as exc:
                            raise RuntimeError(
                                f"Bad numeric price in {source_pdf}, page {page_number}: {row!r}"
                            ) from exc
                        if not price.is_finite() or price < 0:
                            raise RuntimeError(
                                f"Invalid price in {source_pdf}, page {page_number}: {row!r}"
                            )
                        if price == 0:
                            # Retain the literal source cell, but do not turn a
                            # zero placeholder into a retail-price observation.
                            available = False
                            availability_reason = "zero_price_placeholder_omitted"
                            price = None
                        elif price < 10 and not re.search(r"\begg(?:s)?\b", commodity, re.I):
                            # DA reports non-egg agri-fishery prices per kg and
                            # cooking oil by package/liter; a sub-₱10 value is
                            # an implausible source cell and is withheld for review.
                            available = False
                            availability_reason = "implausible_low_price_omitted"
                            price = None
                    if not commodity:
                        availability_reason = availability_reason or "source_row_has_no_commodity_label"
                    raw_rows.append({
                        "source_link_label_date": listing_date.isoformat(),
                        "printed_report_date": None,
                        "report_date": listing_date.isoformat(),
                        "report_date_correction_reason": None,
                        "source_upload_month": _source_upload_month(source_pdf),
                        "source_pdf": source_pdf,
                        "page": page_number,
                        "table_row": row_number,
                        "section": current_section,
                        "commodity": commodity,
                        "specification": specification,
                        "reported_unit": explicit_unit or None,
                        "reported_price": raw_price,
                        "price_index": str(price) if price is not None else None,
                        "available": available,
                        "availability_reason": availability_reason,
                    })

    first_page = page_text[0] if page_text else ""
    title = first_page.casefold()
    title_identifies_dpi = (
        "daily price index" in title
        or (
            "prevailing retail" in title
            and ("agri-fishery commodities" in title or "agricultural and fishery commodities" in title)
            and ("national capital region" in title or "(ncr)" in title)
        )
    )
    if not title_identifies_dpi:
        raise RuntimeError(f"PDF title does not identify a Daily Price Index: {source_pdf}")
    printed_report_date, report_date, date_correction_reason = _resolve_report_date(first_page, listing_date)
    if report_date > listing_date:
        raise RuntimeError(
            f"Resolved report date {report_date} is after DA page link label {listing_date}: {source_pdf}"
        )
    if not START_DATE <= report_date <= LATEST_COVERED_DATE:
        raise RuntimeError(f"Embedded report date outside authorized cutover range: {report_date}: {source_pdf}")
    for row in raw_rows:
        row["printed_report_date"] = printed_report_date.isoformat()
        row["report_date"] = report_date.isoformat()
        row["report_date_correction_reason"] = date_correction_reason
    if table_headers == 0 or not raw_rows:
        raise RuntimeError(f"No structured price table found: {source_pdf}")
    return raw_rows, {
        "source_link_label_date": listing_date.isoformat(),
        "printed_report_date": printed_report_date.isoformat(),
        "report_date": report_date.isoformat(),
        "report_date_correction_reason": date_correction_reason,
        "source_upload_month": _source_upload_month(source_pdf),
        "page_count": len(page_text),
        "structured_table_headers": table_headers,
        "sections": sorted(sections_seen),
        "numeric_rows": sum(row["available"] for row in raw_rows),
        "not_available_rows": sum(not row["available"] for row in raw_rows),
        "reported_na_rows": sum(row["availability_reason"] == "source_not_available_marker" for row in raw_rows),
        "zero_price_rows_omitted": sum(row["availability_reason"] == "zero_price_placeholder_omitted" for row in raw_rows),
        "implausible_low_price_rows_omitted": sum(row["availability_reason"] == "implausible_low_price_omitted" for row in raw_rows),
        "source_calculation_error_rows_omitted": sum(row["availability_reason"] == "source_calculation_error_omitted" for row in raw_rows),
        "unassigned_source_rows": sum(row["availability_reason"] == "source_row_has_no_commodity_label" for row in raw_rows),
        "raw_price_rows": len(raw_rows),
    }


def _strip_origin(text: str) -> tuple[str, str | None]:
    origins = {match.group(1).casefold() for match in ORIGIN_RE.finditer(text)}
    origin = "Imported" if "imported" in origins else ("Local" if "local" in origins else None)
    cleaned = ORIGIN_RE.sub(" ", text)
    cleaned = re.sub(r"\(\s*\)", " ", cleaned)
    cleaned = re.sub(r"[,;/]+\s*[,;/]+", " ", cleaned)
    return _clean(cleaned.strip(" ,;/")), origin


def _section_category(section: str, commodity: str) -> str | None:
    s = section.casefold()
    c = _strip_origin(commodity)[0].casefold()
    # Product labels are stronger evidence than a stale section carried across
    # a page break or a table with a missing section-header cell.
    if c.startswith(FISH_SOURCE_PREFIXES):
        return "Fish"
    if "rice" in c or "rice" in s:
        return "Rice"
    if c.startswith(("corn ", "corn grits", "corn cracked", "yellow sweet corn")) or "corn" in s:
        return "Corn"
    if c.startswith(("beef ", "pork ", "carabeef", "buffalo", "lamb", "frozen kasim", "frozen liempo", "fore shank", "short ribs")):
        return "Livestock"
    if c.startswith(("chicken", "whole chicken", "duck", "whole duck", "peckin duck", "pekin duck")):
        return "Poultry"
    if c.startswith(VEGETABLE_SOURCE_PREFIXES):
        return "Vegetables"
    if c.startswith(FRUIT_SOURCE_PREFIXES):
        return "Fruits"
    if c.startswith("sugar"):
        return "Sugar"
    if c.startswith("cooking oil"):
        return "Oils"
    if s == "products":
        if c.startswith(("beef ", "pork ", "carabeef", "lamb", "frozen kasim", "frozen liempo")):
            return "Livestock"
        if c.startswith(("chicken", "whole chicken", "duck", "peckin duck", "pekin duck")):
            return "Poultry"
    if "rice" in s:
        return "Rice"
    if "corn" in s:
        return "Corn"
    if "legume" in s:
        return "Vegetables" if "mungbean" in c or "mung bean" in c else None
    if "fish" in s:
        return "Fish"
    if any(term in s for term in ("livestock", "beef meat", "pork meat")):
        return "Poultry" if c.startswith(("chicken", "whole chicken", "duck", "peckin")) else "Livestock"
    if "poultry" in s:
        return "Poultry"
    if any(term in s for term in ("vegetable", "spices")):
        return "Vegetables"
    if "fruit" in s:
        return "Fruits"
    if "other basic" in s:
        if c.startswith("sugar"):
            return "Sugar"
        if c.startswith("cooking oil"):
            return "Oils"
    return None


def _variant(*parts: str) -> str:
    values = []
    for part in parts:
        part = _clean(part)
        if not part:
            continue
        part = re.sub(r"\s*\(([^()]*)\)\s*", r" \1 ", part)
        part = re.sub(r"\s+", " ", part).strip(" ,;-/")
        if part and part.casefold() not in {v.casefold() for v in values}:
            values.append(part)
    return " - ".join(values) if values else "Standard"


def _useful_specification(text: str) -> str:
    """Drop prose definitions while retaining concise product specifications."""
    value = _clean(text)
    if not value:
        return ""
    if ";" in value:
        tail = _clean(value.rsplit(";", 1)[-1])
        # Some poultry rows append a brand after prose; preserve that label.
        if len(tail) <= 40 and not re.match(
            r"^(?:the|it|this|which|often|known|consist|cut from)\b", tail, re.I
        ):
            return tail
        return ""
    if len(value) > 100 or re.match(
        r"^(?:cut from|includes? |the .* (?:composed|derived|prepared)|consist(?:s)? of)\b",
        value, re.I,
    ):
        return ""
    if re.search(r"\b(?:often used|known for|composed of|is derived|is prepared|consist(?:s)? of)\b", value, re.I):
        return ""
    return value


def _prefix_rest(text: str, aliases: list[str]) -> tuple[str, str] | None:
    value = _clean(text)
    folded = value.casefold()
    for alias in sorted(aliases, key=len, reverse=True):
        if folded == alias.casefold():
            return alias, ""
        if folded.startswith(alias.casefold()) and (len(value) == len(alias) or value[len(alias)] in " ,(/-"):
            return alias, value[len(alias):].strip(" ,;/")
    return None


FISH_ALIASES = [
    ("Galunggong", "Round Scad"), ("Bangus", "Milkfish"),
    ("Alumahan", "Indian Mackerel"), ("Tilapia", "Tilapia"),
    ("Indian Mackerel", "Indian Mackerel"), ("Mackerel", "Mackerel"),
    ("Sardines", "Sardines"), ("Squid", "Squid"),
    ("Tambakol", "Yellow-Fin Tuna"), ("Yellow-Fin Tuna", "Yellow-Fin Tuna"),
    ("Salmon Belly", "Salmon Belly"), ("Salmon Head", "Salmon Head"),
    ("sssTanigue", "Tanigue"),
    ("Mackerel", "Mackerel"), ("Tanigue", "Tanigue"),
    ("Pampano", "Pampano"), ("Pompano", "Pampano"), ("Bonito", "Bonito"),
]
VEGETABLE_ALIASES = [
    ("Habichuelas/Baguio Beans", "Baguio Beans"),
    ("Habichuelas (Baguio Beans)", "Baguio Beans"),
    ("Native Pechay", "Pechay Tagalog"), ("Pechay (Native)", "Pechay Tagalog"),
    ("Pechay Tagalog", "Pechay Tagalog"), ("Pechay (Baguio)", "Pechay Baguio"),
    ("Pechay Baguio", "Pechay Baguio"), ("Pole Sitao", "String Beans"),
    ("String Beans", "String Beans"), ("Sitao", "String Beans"),
    ("Baguio Beans", "Baguio Beans"), ("Bell Pepper", "Bell Pepper"),
    ("Bittergourd", "Bittergourd"), ("Ampalaya", "Bittergourd"),
    ("Cauliflower", "Cauliflower"), ("Broccoli", "Broccoli"),
    ("Cabbage", "Cabbage"), ("Carrots", "Carrot"), ("Carrot", "Carrot"),
    ("Celery", "Celery"), ("Chayote", "Chayote"), ("Eggplant", "Eggplant"),
    ("Lettuce", "Lettuce"), ("White Potato", "Potato"), ("Potato", "Potato"),
    ("Chilli", "Chili"), ("Chili", "Chili"), ("Tiger Chillies", "Chili"),
    ("Garlic", "Garlic"), ("Ginger", "Ginger"), ("Red Onion", "Red Onion"),
    ("White Onion", "White Onion"), ("Squash", "Squash"), ("Tomato", "Tomato"),
]
FRUIT_ALIASES = [
    ("Calamansi", "Calamansi"), ("Banana", "Banana"), ("Mango", "Mango"),
    ("Avocado", "Avocado"), ("Melon", "Melon"), ("Papaya", "Papaya"),
    ("Pomelo", "Pomelo"), ("Watermelon", "Watermelon"),
]


def _source_identity(raw: dict) -> dict | None:
    section = raw["section"]
    commodity = raw["commodity"]
    spec = raw["specification"]
    full_text = f"{commodity} {spec}"
    clean_commodity, row_origin = _strip_origin(commodity)
    clean_spec, spec_origin = _strip_origin(spec)
    variant_spec = _useful_specification(clean_spec)
    origin = row_origin or spec_origin or "Local"
    category = _section_category(section, commodity)
    if category is None:
        return None

    product = ""
    variant = "Standard"

    if category == "Rice":
        product = "Rice"
        section_folded = section.casefold()
        if "imported" in section_folded:
            origin = "Imported"
        elif "local" in section_folded:
            origin = "Local"
        elif row_origin or spec_origin:
            origin = row_origin or spec_origin
        else:
            return None
        label = _clean(f"{clean_commodity} {variant_spec}")
        label = re.sub(r"\bRice\b", "", label, flags=re.I)
        label = _clean(label)
        if label.casefold().startswith(("fancy white", "special/fancy", "other special")):
            label = re.sub(r"^(?:Fancy White|Special/Fancy|Other Special)(?:\s+White)?", "Special", label, flags=re.I)
        variant = _variant(label)

    elif category == "Corn":
        line = _clean(f"{clean_commodity} {clean_spec}")
        folded = line.casefold()
        if "cracked" in folded:
            product, variant = "Corn Cracked", _variant("Yellow (Feed Grade)")
        elif "grits" in folded:
            product = "Corn Grits"
            detail = "Feed Grade" if "feed grade" in folded else (
                "White (Food Grade)" if "white" in folded else "Yellow (Food Grade)"
            )
            variant = _variant(detail)
        elif "yellow" in folded:
            product, variant = "Yellow Sweet Corn", _variant("Cob")
        elif "white" in folded:
            product, variant = "Corn", _variant("White")
        else:
            return None

    elif category == "Fish":
        if re.search(r"\b(?:indian mackerel|tamban|pusit bisaya|yellow[- ]fin tuna)\b", clean_commodity, re.I):
            clean_commodity = re.sub(
                r"\((?:Indian Mackerel|Tamban|Pusit Bisaya|Yellow[- ]Fin Tuna)\)",
                "", clean_commodity, flags=re.I)
        match = _prefix_rest(clean_commodity, [alias for alias, _ in FISH_ALIASES])
        if match:
            alias, rest = match
            product = next(name for source, name in FISH_ALIASES if source.casefold() == alias.casefold())
            variant = _variant(rest, variant_spec)
        else:
            # Unknown commodities require a reviewed crosswalk; never guess a
            # FOODCAST identity from a source label.
            return None

    elif category == "Livestock":
        text = _clean(f"{clean_commodity} {variant_spec}")
        folded = text.casefold()
        if folded.startswith("frozen kasim"):
            product, variant = "Pork", _variant("Frozen Ham")
        elif folded.startswith("frozen liempo"):
            product, variant = "Pork", _variant("Frozen Belly")
        elif folded.startswith("beef "):
            product, variant = "Beef", _variant(text[5:])
        elif folded.startswith("pork "):
            product = "Pork"
            cut = text[5:]
            cut = re.sub(r"\bHam\s*/\s*Kasim\b", "Ham", cut, flags=re.I)
            cut = re.sub(r"\bBelly\s*/\s*Liempo\b", "Belly", cut, flags=re.I)
            cut = re.sub(r"\bHind Leg\s*/\s*Pigue\b", "Hind Leg", cut, flags=re.I)
            cut = re.sub(r"\bSpareribs\b", "Spare Ribs", cut, flags=re.I)
            cut = re.sub(r"\bPicnic Shoulder\s*\(Kasim\)", "Ham", cut, flags=re.I)
            cut = re.sub(r"\bHam\s*\(Kasim\)", "Ham", cut, flags=re.I)
            cut = re.sub(r"\bBelly\s*\(Liempo\)", "Belly", cut, flags=re.I)
            cut = re.sub(r"\bHind Leg\s*\(Pigue\)", "Hind Leg", cut, flags=re.I)
            variant = _variant(cut)
        elif folded.startswith("fore shank"):
            product, variant = "Pork", _variant(text)
        elif folded.startswith(("carabeef", "buffalo")):
            prefix = "Carabeef" if folded.startswith("carabeef") else "Buffalo"
            product, variant = "Carabeef", _variant(text[len(prefix):])
        elif folded.startswith("short ribs"):
            product, variant = "Beef", _variant("Short Ribs")
        elif folded.startswith("lamb"):
            product, variant = "Lamb", _variant(text[len("Lamb"):])
        else:
            return None

    elif category == "Poultry":
        text = _clean(f"{clean_commodity} {variant_spec}")
        folded = text.casefold()
        egg = re.match(r"Chicken Egg\s*\(([^)]*)\)", clean_commodity, re.I)
        if egg:
            product = "Chicken Egg"
            egg_detail = _clean(egg.group(1)).replace(",", " ")
            variant = _variant(egg_detail)
        elif folded.startswith("whole chicken"):
            product, variant = "Chicken", _variant("Whole", text[len("Whole Chicken"):])
        elif folded.startswith("whole duck"):
            product, variant = "Duck", _variant("Whole", text[len("Whole Duck"):])
        elif folded.startswith("chicken "):
            product, variant = "Chicken", _variant(text[len("Chicken "):])
        elif folded.startswith("duck meat"):
            product, variant = "Duck", _variant("Meat", variant_spec)
        elif folded.startswith("peckin duck") or folded.startswith("pekin duck"):
            product, variant = "Duck", _variant("Pekin", variant_spec)
        else:
            return None

    elif category == "Vegetables":
        if "legume" in section.casefold():
            product, variant = "Mung Beans", _variant(variant_spec)
        else:
            aliases = [alias for alias, _ in VEGETABLE_ALIASES]
            match = _prefix_rest(clean_commodity, aliases)
            if not match:
                return None
            alias, rest = match
            product = next(name for source, name in VEGETABLE_ALIASES if source.casefold() == alias.casefold())
            detail = _variant(rest, variant_spec)
            if product == "Garlic" and detail.casefold() == "native":
                variant = "Native"
            else:
                variant = detail

    elif category == "Fruits":
        match = _prefix_rest(clean_commodity, [alias for alias, _ in FRUIT_ALIASES])
        if not match:
            return None
        alias, rest = match
        product = next(name for source, name in FRUIT_ALIASES if source.casefold() == alias.casefold())
        variant = _variant(rest, variant_spec)

    elif category == "Sugar":
        product = "Sugar"
        label = _clean(f"{clean_commodity} {variant_spec}")
        variant = _variant(re.sub(r"^Sugar\s*", "", label, flags=re.I))

    elif category == "Oils":
        label = _clean(f"{clean_commodity} {clean_spec}")
        folded = label.casefold()
        if "coconut" in folded:
            product, label = "Coconut Oil", re.sub(r"^Cooking Oil\s*", "", label, flags=re.I)
        elif "palm" in folded:
            product, label = "Palm Oil", re.sub(r"^Cooking Oil\s*", "", label, flags=re.I)
        else:
            product, label = "Cooking Oil", re.sub(r"^Cooking Oil\s*", "", label, flags=re.I)
        label = re.sub(r"\b(?:350\s*ml|500\s*ml)\s*/\s*bottle\b", lambda m: re.sub(r"\s+", "", m.group(0).split("/")[0]), label, flags=re.I)
        label = re.sub(r"\b1\s*,\s*000\s*ml\s*/\s*bottle\b", "1L", label, flags=re.I)
        label = re.sub(r"\b1\s*Liter\s*/\s*bottle\b", "1L", label, flags=re.I)
        variant = _variant(label)

    if not product:
        return None

    source_unit = _clean(raw.get("reported_unit") or "")
    if category == "Oils":
        # Oil rows are published as specific packages (e.g. 350 ml/bottle).
        # The package size is retained in both the variant and unit so the
        # source's unmodified per-package value is not mislabeled as per liter.
        size = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\s*(ml|milliliters?|l|liters?|litres?)\b", clean_spec, re.I)
        if size:
            amount = Decimal(size.group(1).replace(",", ""))
            if amount <= 0:
                raise RuntimeError(f"Cooking-oil package size is not positive: {clean_spec!r}")
            source_volume = size.group(2).casefold()
            if source_volume in {"ml", "milliliter", "milliliters"}:
                if source_unit and source_unit.casefold() not in {"ml", "milliliter", "milliliters"}:
                    raise RuntimeError(f"Oil package/price unit conflict: {source_unit!r} vs {clean_spec!r}")
                unit = f"{format(amount.normalize(), 'f')}ml"
            else:
                if source_unit and source_unit.casefold() not in {"l", "liter", "litre", "per liter", "per litre"}:
                    raise RuntimeError(f"Oil package/price unit conflict: {source_unit!r} vs {clean_spec!r}")
                unit = "liter" if amount == 1 else f"{format(amount.normalize(), 'f')}L"
        else:
            if source_unit and source_unit.casefold() not in {"l", "liter", "litre", "per liter", "per litre"}:
                raise RuntimeError(f"Cooking-oil row lacks an interpretable package size: {source_unit!r}")
            # Some branded rows have no size specification; the DA notes define
            # those rows in liters.
            unit = "liter"
    elif category == "Poultry" and product == "Chicken Egg":
        if source_unit and source_unit.casefold() not in {"pc", "pcs", "piece", "pieces", "per piece"}:
            raise RuntimeError(f"Unexpected DA egg price unit: {source_unit!r}")
        unit = "piece"
    else:
        if source_unit and source_unit.casefold() not in {"kg", "kilogram", "kilograms", "per kg"}:
            raise RuntimeError(f"Unexpected DA commodity price unit: {source_unit!r}")
        unit = "kg"

    price = Decimal(raw["price_index"])
    return {
        "product_category": category,
        "product_name": product,
        "product_variant": variant,
        "origin": origin,
        "unit": unit,
        "price_index": format(price, "f"),
        "report_date": raw["report_date"],
        "source_pdf": raw["source_pdf"],
    }


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _write_sql(path: Path, records: list[dict], end_exclusive: date) -> None:
    columns = (
        "product_category, product_name, product_variant, origin, unit, "
        "price_index, report_date, source_pdf"
    )
    lines = [
        "-- Local source replacement artifact generated from official DA Daily Price Index PDFs.",
        "-- Review before execution. This file has NOT been executed against Supabase.",
        "-- Executing it would violate the current FOODCAST Supabase read-only mission policy.",
        f"-- Cutover range: {START_DATE.isoformat()} <= report_date < {end_exclusive.isoformat()}.",
        "-- Pre-cutover legacy rows remain; train/evaluate from the DPI source only until a reviewed source-aware policy exists.",
        "-- Missing reports and n/a observations are omitted; no values are forward-filled.",
        "-- DA link dates and upload-folder months do not establish first availability; these rows alone are not point-in-time backtest evidence.",
        "-- Product names are limited to the frozen FOODCAST snapshot crosswalk; unmatched source commodities remain in local raw evidence.",
        "BEGIN;",
        f"DELETE FROM public.food_prices WHERE report_date >= DATE '{START_DATE.isoformat()}' AND report_date < DATE '{end_exclusive.isoformat()}';",
    ]
    chunk_size = 500
    for offset in range(0, len(records), chunk_size):
        chunk = records[offset:offset + chunk_size]
        lines.append(f"INSERT INTO public.food_prices ({columns}) VALUES")
        values = []
        for row in chunk:
            values.append("(" + ", ".join((
                _sql_literal(row["product_category"]),
                _sql_literal(row["product_name"]),
                _sql_literal(row["product_variant"]),
                _sql_literal(row["origin"]),
                _sql_literal(row["unit"]),
                row["price_index"],
                f"DATE {_sql_literal(row['report_date'])}",
                _sql_literal(row["source_pdf"]),
            )) + ")")
        lines.append(",\n".join(values) + ";")
    lines.extend(["COMMIT;", ""])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _map_source_rows(raw_rows: list[dict]) -> tuple[list[dict], dict]:
    parsed = []
    excluded = Counter()
    unmapped = []
    excluded_rows = []
    unassigned = []
    unsupported_names = Counter()
    for raw in raw_rows:
        if not raw["available"]:
            continue
        mapped = _source_identity(raw)
        if mapped is None:
            section = raw["section"] or "(unsectioned)"
            excluded[section] += 1
            reason = "source_row_has_no_commodity_label" if not raw["commodity"] else "outside_foodcast_supported_categories"
            if raw["commodity"] and _section_category(raw["section"], raw["commodity"]) is not None:
                reason = "foodcast_mapping_unresolved"
                unmapped.append({
                    "section": raw["section"], "commodity": raw["commodity"],
                    "specification": raw["specification"], "price_index": raw["price_index"],
                })
            excluded_rows.append({
                "section": raw["section"], "commodity": raw["commodity"],
                "specification": raw["specification"], "price_index": raw["price_index"],
                "exclusion_reason": reason,
            })
            if not raw["commodity"]:
                unassigned.append({
                    "section": raw["section"], "source_pdf": raw["source_pdf"],
                    "page": raw["page"], "table_row": raw["table_row"],
                    "reported_price": raw["reported_price"],
                })
            continue
        if (mapped["product_category"], mapped["product_name"]) not in FOODCAST_PRODUCT_NAMES:
            excluded["unsupported FOODCAST product name"] += 1
            unsupported_names[(mapped["product_category"], mapped["product_name"])] += 1
            excluded_rows.append({
                "section": raw["section"], "commodity": raw["commodity"],
                "specification": raw["specification"], "price_index": raw["price_index"],
                "proposed_product_name": mapped["product_name"],
                "exclusion_reason": "product name absent from FOODCAST snapshot crosswalk",
            })
            continue
        parsed.append(mapped)
    return parsed, {
        "supported_rows": len(parsed),
        "excluded_numeric_rows": sum(excluded.values()),
        "excluded_by_section": dict(excluded),
        "excluded_numeric_rows_detail": excluded_rows,
        "unassigned_source_rows": unassigned,
        "unmapped_supported_rows": unmapped,
        "unsupported_foodcast_product_rows": sum(unsupported_names.values()),
        "unsupported_foodcast_product_names": {
            f"{category}/{name}": count
            for (category, name), count in sorted(unsupported_names.items())
        },
    }


def _upgrade_report_date_metadata(item: dict, source_rows: list[dict]) -> None:
    link_label = item.get("source_link_label_date", item.get("archive_listing_date"))
    if not link_label:
        raise RuntimeError(f"Cached report is missing its DA page link-label date: {item.get('source_pdf')}")
    report_date = date.fromisoformat(item["report_date"])
    if report_date.isoformat() == link_label:
        printed_date, resolved_date, correction = report_date, report_date, None
    else:
        cached_pdf = SOURCE_PDF_DIR / f"{link_label}.pdf"
        with pdfplumber.open(cached_pdf) as pdf:
            first_page = pdf.pages[0].extract_text() or ""
        printed_date, resolved_date, correction = _resolve_report_date(
            first_page, date.fromisoformat(link_label)
        )
    item["source_link_label_date"] = link_label
    item["printed_report_date"] = printed_date.isoformat()
    item["report_date"] = resolved_date.isoformat()
    item["report_date_correction_reason"] = correction
    item["source_upload_month"] = _source_upload_month(item["source_pdf"])
    item.pop("archive_listing_date", None)
    item.pop("selected_version_listing_date", None)
    for row in source_rows:
        row["source_link_label_date"] = link_label
        row["printed_report_date"] = printed_date.isoformat()
        row["report_date"] = resolved_date.isoformat()
        row["report_date_correction_reason"] = correction
        row["source_upload_month"] = item["source_upload_month"]
        row.pop("archive_listing_date", None)


def _parse_pdf(listing_date: date, url: str) -> tuple[list[dict], dict, str]:
    cached_pdf = SOURCE_PDF_DIR / f"{listing_date.isoformat()}.pdf"
    if cached_pdf.exists():
        content = cached_pdf.read_bytes()
    else:
        time.sleep(0.15)
        content = _curl(url)
        if not content.startswith(b"%PDF-"):
            raise RuntimeError(f"Response is not a PDF: {url}")
        cached_pdf.write_bytes(content)
    raw_rows, report_stats = _extract_table_rows(content, listing_date, url)
    parsed, mapping_stats = _map_source_rows(raw_rows)
    stats = {
        **report_stats,
        **mapping_stats,
        "content_sha256": sha256(content).hexdigest(),
        "content_bytes": len(content),
        "raw_rows": raw_rows,
    }
    return parsed, stats, sha256(content).hexdigest()


def build() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_PDF_DIR.mkdir(parents=True, exist_ok=True)
    if not FOODCAST_NAMES_REFERENCE.exists():
        raise RuntimeError(f"FOODCAST canonical-name reference snapshot is missing: {FOODCAST_NAMES_REFERENCE}")
    foodcast_reference_bytes = FOODCAST_NAMES_REFERENCE.read_bytes()
    foodcast_reference_rows = json.loads(foodcast_reference_bytes.decode("utf-8"))
    snapshot_product_names = {
        (row["product_category"], _clean(row["product_name"]))
        for row in foodcast_reference_rows
    }
    if snapshot_product_names != FOODCAST_PRODUCT_NAMES:
        raise RuntimeError("Configured FOODCAST product-name crosswalk differs from its frozen local snapshot")
    foodcast_reference_sha256 = sha256(foodcast_reference_bytes).hexdigest()
    links, discovery_method, discovery_sha256 = discover_pdfs()
    if links[0][0] != START_DATE or links[-1][0] != LATEST_COVERED_DATE:
        raise RuntimeError(
            f"Official archive bounds changed: {links[0][0]} through {links[-1][0]}"
        )
    if len({d for d, _ in links}) != len(links):
        raise RuntimeError("Duplicate report dates in the official PDF listing")

    current_parser_sha256 = sha256(Path(__file__).read_bytes()).hexdigest()
    candidate_records: list[dict] = []
    raw_evidence: list[dict] = []
    report_manifest: list[dict] = []
    failures: list[dict] = []
    pending_links = links
    reused_pdf_count = 0
    resume_source_manifest_sha256 = None
    prior_manifest_path = OUTPUT_DIR / "manifest.json"
    prior_rows_path = OUTPUT_DIR / "canonical_rows.json"
    prior_raw_path = OUTPUT_DIR / "daily_price_index_raw_rows.jsonl"
    if prior_manifest_path.exists() and prior_rows_path.exists() and prior_raw_path.exists():
        prior_manifest_bytes = prior_manifest_path.read_bytes()
        prior_manifest = json.loads(prior_manifest_bytes.decode("utf-8"))
        prior_failures = prior_manifest.get("failures", [])
        resumable_failures = [
            failure for failure in prior_failures
            if failure.get("error", "").startswith("PDF title does not identify a Daily Price Index:")
        ]
        prior_link_map = {
            item.get("source_link_label_date", item.get("archive_listing_date")): item["source_pdf"]
            for item in prior_manifest.get("reports", [])
        }
        prior_link_map.update({
            item.get("source_link_label_date", item.get("archive_listing_date")): item["source_pdf"]
            for item in prior_failures
        })
        current_link_map = {day.isoformat(): url for day, url in links}
        prior_code_sha256 = prior_manifest.get("code_sha256")
        resumable_checkpoint = prior_code_sha256 in {
            RESUMABLE_TITLE_GATE_CODE_SHA256, RESUMABLE_COMPLETE_PARSE_CODE_SHA256,
        }
        complete_mapping_checkpoint = (
            prior_code_sha256 == RESUMABLE_COMPLETE_PARSE_CODE_SHA256
            and not prior_failures and not prior_manifest.get("errors")
            and len(prior_manifest.get("reports", [])) == len(links)
        )
        can_resume = (
            resumable_checkpoint
            and len(resumable_failures) == len(prior_failures)
            and len(prior_manifest.get("reports", [])) + len(prior_failures) == len(links)
            and prior_link_map == current_link_map
        )
        if can_resume:
            for item in prior_manifest.get("reports", []):
                link_label = item.get("source_link_label_date", item.get("archive_listing_date"))
                cached = SOURCE_PDF_DIR / f"{link_label}.pdf"
                if not cached.exists() or sha256(cached.read_bytes()).hexdigest() != item["sha256"]:
                    can_resume = False
                    break
        if can_resume:
            with prior_raw_path.open("r", encoding="utf-8") as raw_file:
                raw_evidence = [json.loads(line) for line in raw_file if line.strip()]
            report_manifest = prior_manifest["reports"]
            for item in report_manifest:
                item.setdefault("parser_code_sha256", prior_code_sha256)
            if complete_mapping_checkpoint:
                raw_by_source: dict[str, list[dict]] = defaultdict(list)
                for raw in raw_evidence:
                    raw_by_source[raw["source_pdf"]].append(raw)
                for item in report_manifest:
                    source_pdf = item["source_pdf"]
                    source_rows = raw_by_source.get(source_pdf, [])
                    link_label = item.get("source_link_label_date", item.get("archive_listing_date"))
                    if link_label in LAYOUT_REFRESH_LINK_LABEL_DATES:
                        parsed, stats, digest = _parse_pdf(date.fromisoformat(link_label), source_pdf)
                        raw_evidence = [row for row in raw_evidence if row["source_pdf"] != source_pdf]
                        source_rows = stats["raw_rows"]
                        raw_by_source[source_pdf] = source_rows
                        raw_evidence.extend(source_rows)
                        mapping_stats = {key: value for key, value in stats.items() if key in {
                            "supported_rows", "excluded_numeric_rows", "excluded_by_section",
                            "excluded_numeric_rows_detail", "unassigned_source_rows",
                            "unmapped_supported_rows", "unsupported_foodcast_product_rows",
                            "unsupported_foodcast_product_names",
                        }}
                        item.update({
                            "source_link_label_date": stats["source_link_label_date"],
                            "printed_report_date": stats["printed_report_date"],
                            "report_date": stats["report_date"],
                            "report_date_correction_reason": stats["report_date_correction_reason"],
                            "source_upload_month": stats["source_upload_month"],
                            "sha256": digest, "bytes": stats["content_bytes"],
                            "page_count": stats["page_count"],
                            "raw_price_rows": stats["raw_price_rows"],
                            "numeric_rows": stats["numeric_rows"],
                            "not_available_rows": stats["not_available_rows"],
                            "reported_na_rows": stats["reported_na_rows"],
                            "parser_code_sha256": current_parser_sha256,
                        })
                    else:
                        _upgrade_report_date_metadata(item, source_rows)
                        parsed, mapping_stats = _map_source_rows(source_rows)
                    candidate_records.extend(parsed)
                    item.update(mapping_stats)
                pending_links = []
            else:
                candidate_records = json.loads(prior_rows_path.read_text(encoding="utf-8"))
                failed_days = {item.get("source_link_label_date", item.get("archive_listing_date")) for item in prior_failures}
                pending_links = [(day, url) for day, url in links if day.isoformat() in failed_days]
            reused_pdf_count = len(report_manifest)
            resume_source_manifest_sha256 = sha256(prior_manifest_bytes).hexdigest()
            print(
                f"Resuming verified {'complete' if complete_mapping_checkpoint else 'partial'} parse: "
                f"reusing {reused_pdf_count} PDFs; parsing {len(pending_links)} remaining PDFs",
                flush=True,
            )

    completed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(_parse_pdf, day, url): (day, url) for day, url in pending_links}
        for future in as_completed(future_map):
            day, url = future_map[future]
            try:
                parsed, stats, digest = future.result()
                candidate_records.extend(parsed)
                raw_evidence.extend(stats["raw_rows"])
                report_manifest.append({
                    "source_link_label_date": stats["source_link_label_date"],
                    "printed_report_date": stats["printed_report_date"],
                    "report_date": stats["report_date"], "source_pdf": url,
                    "report_date_correction_reason": stats["report_date_correction_reason"],
                    "source_upload_month": stats["source_upload_month"],
                    "parser_code_sha256": current_parser_sha256,
                    "sha256": digest, "bytes": stats["content_bytes"],
                    "page_count": stats["page_count"],
                    "raw_price_rows": stats["raw_price_rows"],
                    "numeric_rows": stats["numeric_rows"],
                    "not_available_rows": stats["not_available_rows"],
                    "reported_na_rows": stats["reported_na_rows"],
                    "supported_rows": stats["supported_rows"],
                    "excluded_numeric_rows": stats["excluded_numeric_rows"],
                    "excluded_by_section": stats["excluded_by_section"],
                    "unmapped_supported_rows": stats["unmapped_supported_rows"],
                    "excluded_numeric_rows_detail": stats["excluded_numeric_rows_detail"],
                    "unsupported_foodcast_product_rows": stats["unsupported_foodcast_product_rows"],
                    "unsupported_foodcast_product_names": stats["unsupported_foodcast_product_names"],
                    "zero_price_rows_omitted": stats["zero_price_rows_omitted"],
                    "implausible_low_price_rows_omitted": stats["implausible_low_price_rows_omitted"],
                    "source_calculation_error_rows_omitted": stats["source_calculation_error_rows_omitted"],
                    "unassigned_source_rows": stats["unassigned_source_rows"],
                })
            except Exception as exc:
                failures.append({"source_link_label_date": day.isoformat(), "source_pdf": url, "error": str(exc)})
            completed += 1
            if completed % 10 == 0 or completed == len(pending_links):
                print(f"Processed {completed}/{len(pending_links)} pending DPI PDFs; failures={len(failures)}", flush=True)

    selected_source_by_report: dict[str, str] = {}
    reports_by_date: dict[str, list[dict]] = defaultdict(list)
    for item in report_manifest:
        reports_by_date[item["report_date"]].append(item)
    version_selection_conflicts = []
    for report_date, candidates in reports_by_date.items():
        exact_label = [item for item in candidates if item["source_link_label_date"] == report_date]
        if len(candidates) == 1:
            selected_item = candidates[0]
        elif len(exact_label) == 1:
            selected_item = exact_label[0]
        elif len({item["sha256"] for item in candidates}) == 1:
            selected_item = sorted(candidates, key=lambda item: item["source_link_label_date"])[0]
        else:
            version_selection_conflicts.append({
                "report_date": report_date,
                "candidate_sources": [
                    {"source_link_label_date": item["source_link_label_date"], "source_pdf": item["source_pdf"], "sha256": item["sha256"]}
                    for item in candidates
                ],
            })
            continue
        selected_source_by_report[report_date] = selected_item["source_pdf"]
    for item in report_manifest:
        report_date = item["report_date"]
        selected = item["source_pdf"] == selected_source_by_report.get(report_date)
        item["selected_for_report_date"] = selected
        item["selected_source_link_label_date"] = next(
            (candidate["source_link_label_date"] for candidate in reports_by_date[report_date]
             if candidate["source_pdf"] == selected_source_by_report.get(report_date)),
            None,
        )
    for row in raw_evidence:
        row["selected_for_report_date"] = (
            row["source_pdf"] == selected_source_by_report.get(row["report_date"])
        )
    records = [
        row for row in candidate_records
        if row["source_pdf"] == selected_source_by_report.get(row["report_date"])
    ]
    report_manifest.sort(key=lambda item: (item["report_date"], item["source_link_label_date"]))
    failures.sort(key=lambda item: item["source_link_label_date"])
    missing_dates = []
    expected = START_DATE
    by_date = {
        date.fromisoformat(item["report_date"])
        for item in report_manifest if item["selected_for_report_date"]
    }
    while expected <= LATEST_COVERED_DATE:
        if expected not in by_date:
            missing_dates.append(expected.isoformat())
        expected = date.fromordinal(expected.toordinal() + 1)

    key_counts = Counter((
        row["report_date"], row["product_name"], row["product_variant"], row["origin"]
    ) for row in records)
    duplicate_keys = [key for key, count in key_counts.items() if count > 1]
    unmapped = [
        {"report_date": item["report_date"], "source_pdf": item["source_pdf"], "rows": item["unmapped_supported_rows"]}
        for item in report_manifest if item["selected_for_report_date"] and item["unmapped_supported_rows"]
    ]
    errors = []
    if failures:
        errors.append(f"{len(failures)} PDF(s) failed download or validation")
    if unmapped:
        errors.append(f"{sum(len(item['rows']) for item in unmapped)} supported numeric row(s) need a product mapping")
    if duplicate_keys:
        errors.append(f"{len(duplicate_keys)} duplicate canonical keys found")
    if len(report_manifest) != len(links):
        errors.append(f"only {len(report_manifest)} of {len(links)} listed PDFs parsed")
    if LATEST_COVERED_DATE.isoformat() not in selected_source_by_report:
        errors.append("latest embedded report date does not reach the authorized archive bound")
    if version_selection_conflicts:
        errors.append(f"{len(version_selection_conflicts)} conflicting report-date versions lack safe selection evidence")

    # Stable ordering makes the extracted evidence byte-for-byte reproducible
    # for an unchanged set of source PDFs, independent of network timing.
    records.sort(key=lambda row: (
        row["report_date"], row["product_name"], row["product_variant"], row["origin"]
    ))
    raw_evidence.sort(key=lambda row: (
        row["report_date"], row["source_link_label_date"], row["page"],
        row["table_row"], row["commodity"], row["specification"]
    ))

    selected_reports = [item for item in report_manifest if item["selected_for_report_date"]]
    selected_unsupported_names = Counter()
    selected_exclusions_by_reason = Counter()
    for item in selected_reports:
        selected_unsupported_names.update(item.get("unsupported_foodcast_product_names", {}))
        for row in item.get("excluded_numeric_rows_detail", []):
            selected_exclusions_by_reason[row.get("exclusion_reason", "unspecified")] += 1
    late_upload_months = [
        {"report_date": item["report_date"], "source_upload_month": item["source_upload_month"], "source_pdf": item["source_pdf"]}
        for item in selected_reports
        if item.get("source_upload_month") and item["source_upload_month"] > item["report_date"][:7]
    ]
    snapshot_material = "\n".join(
        f"{item['source_link_label_date']}|{item['printed_report_date']}|{item['report_date']}|{item['sha256']}|{item['source_pdf']}"
        for item in report_manifest
    )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_listing": DA_INDEX_URL,
        "foodcast_name_reference_snapshot": FOODCAST_NAMES_REFERENCE.relative_to(ROOT).as_posix(),
        "foodcast_name_reference_sha256": foodcast_reference_sha256,
        "foodcast_name_reference_rows": len(foodcast_reference_rows),
        "foodcast_product_names_allowed": [list(item) for item in sorted(FOODCAST_PRODUCT_NAMES)],
        "foodcast_synonym_crosswalk": {"Fish/Alumahan (Indian Mackerel)": "Fish/Indian Mackerel"},
        "archive_discovery_method": discovery_method,
        "archive_link_capture_sha256": discovery_sha256,
        "link_date_semantics": "DA page link label; this is not a first-publication timestamp.",
        "first_publication_timestamp_available": False,
        "source_url_upload_month_semantics": "Year/month directory in the DA media URL; it can show later file placement but not the exact publication or first-availability time.",
        "cutover_start_inclusive": START_DATE.isoformat(),
        "latest_report_date_inclusive": LATEST_COVERED_DATE.isoformat(),
        "cutover_end_exclusive": date.fromordinal(LATEST_COVERED_DATE.toordinal() + 1).isoformat(),
        "listed_pdf_count": len(links),
        "parsed_pdf_count": len(report_manifest),
        "selected_report_date_count": len(selected_reports),
        "superseded_archive_pdf_count": len(report_manifest) - len(selected_reports),
        "source_snapshot_sha256": sha256(snapshot_material.encode("utf-8")).hexdigest(),
        "code_sha256": current_parser_sha256,
        "reused_pdf_count": reused_pdf_count,
        "resume_source_manifest_sha256": resume_source_manifest_sha256,
        "pdfs_by_parser_code_sha256": dict(Counter(item["parser_code_sha256"] for item in report_manifest)),
        "version_selection_rule": "For duplicate resolved report dates, select a unique PDF whose DA link-label date equals the resolved report date. If only identical PDF content is duplicated, choose deterministically; conflicting nonidentical versions without an exact date match fail closed.",
        "late_publication_limit": "Exact first-publication/availability times and historical revisions are unavailable. Report dates use the printed monitoring date except when the DA link label and printed weekday agree and the printed day number conflicts.",
        "report_date_corrections": [
            {"source_link_label_date": item["source_link_label_date"], "printed_report_date": item["printed_report_date"],
             "report_date": item["report_date"], "reason": item["report_date_correction_reason"],
             "source_pdf": item["source_pdf"]}
            for item in selected_reports if item.get("report_date_correction_reason")
        ],
        "url_upload_month_after_report_month_count": len(late_upload_months),
        "url_upload_month_after_report_month": late_upload_months,
        "selected_versions": [
            {"report_date": item["report_date"], "source_link_label_date": item["source_link_label_date"],
             "printed_report_date": item["printed_report_date"], "source_upload_month": item["source_upload_month"],
             "source_pdf": item["source_pdf"]}
            for item in selected_reports
        ],
        "missing_report_dates_not_filled": missing_dates,
        "numeric_pdf_rows": sum(item["numeric_rows"] for item in report_manifest),
        "n_a_pdf_rows_omitted": sum(item["reported_na_rows"] for item in report_manifest),
        "zero_price_rows_omitted": sum(item["zero_price_rows_omitted"] for item in report_manifest),
        "implausible_low_price_rows_omitted": sum(item["implausible_low_price_rows_omitted"] for item in report_manifest),
        "source_calculation_error_rows_omitted": sum(item["source_calculation_error_rows_omitted"] for item in report_manifest),
        "selected_n_a_rows_omitted": sum(item["reported_na_rows"] for item in selected_reports),
        "selected_excluded_numeric_rows": sum(item["excluded_numeric_rows"] for item in selected_reports),
        "selected_unsupported_foodcast_product_rows": sum(item.get("unsupported_foodcast_product_rows", 0) for item in selected_reports),
        "selected_unsupported_foodcast_product_names": dict(sorted(selected_unsupported_names.items())),
        "selected_exclusions_by_reason": dict(sorted(selected_exclusions_by_reason.items())),
        "unassigned_source_rows": sum(len(item["unassigned_source_rows"]) for item in selected_reports),
        "all_versions_unassigned_source_rows": sum(len(item["unassigned_source_rows"]) for item in report_manifest),
        "canonical_rows": len(records),
        "raw_rows_preserved": len(raw_evidence),
        "excluded_numeric_rows": sum(item["excluded_numeric_rows"] for item in report_manifest),
        "experiment_allowance_consumed": 0,
        "supabase_reads_or_writes": 0,
        "oil_unit_mapping": "Preserve source package size in the unit when stated; preserve raw price values without conversion. Branded rows without package size use the DA-stated liter unit.",
        "errors": errors,
        "failures": failures,
        "unmapped_supported_rows": unmapped,
        "unassigned_source_rows_detail": [
            {"report_date": item["report_date"], "source_pdf": item["source_pdf"],
             "rows": item["unassigned_source_rows"]}
            for item in report_manifest if item["selected_for_report_date"] and item["unassigned_source_rows"]
        ],
        "duplicate_keys": [list(key) for key in duplicate_keys[:50]],
        "reports": report_manifest,
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "canonical_rows.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "daily_price_index_raw_rows.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in raw_evidence),
        encoding="utf-8", newline="\n",
    )
    if errors:
        raise RuntimeError("Export refused: " + "; ".join(errors))

    sql_path = OUTPUT_DIR / "daily_price_index_replace_20250301_through_20261023.sql"
    _write_sql(sql_path, records, date.fromordinal(LATEST_COVERED_DATE.toordinal() + 1))
    manifest["sql_file"] = sql_path.name
    manifest["sql_sha256"] = sha256(sql_path.read_bytes()).hexdigest()
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "SQL_READY_FOR_REVIEW_NOT_EXECUTED",
        "pdfs": len(report_manifest),
        "selected_report_dates": len(selected_reports),
        "canonical_rows": len(records),
        "n_a_rows_omitted": manifest["n_a_pdf_rows_omitted"],
        "missing_report_dates": len(missing_dates),
        "excluded_numeric_rows": manifest["excluded_numeric_rows"],
        "sql_file": str(sql_path),
        "sql_sha256": manifest["sql_sha256"],
    }, indent=2))
    return manifest


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"FAILED CLOSED: {exc}", file=sys.stderr)
        raise
