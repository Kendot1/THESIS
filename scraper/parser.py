"""Extract and validate DA Daily Price Index PDFs before structured parsing."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import re

import pdfplumber
import requests

try:
    from .utils import extract_date_from_url
except ImportError:  # Script execution from the scraper directory.
    from utils import extract_date_from_url


def _matches_report_date(text: str, report_date: date) -> bool:
    month = re.escape(report_date.strftime("%B"))
    pattern = rf"\b(?:{month}\s+0?{report_date.day},?\s+{report_date.year}|0?{report_date.day}\s+{month},?\s+{report_date.year})\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


def parse_daily_tables(pages, report_date, url, *, raw_only=False):
    """Reuse the existing offline DPI cell grouping and FOODCAST crosswalk.

    Do not call the historical rebuild entry point: its date bounds and file
    caches belong to a separate contract. No AI or credentials are required.
    """
    if __package__:
        from . import build_daily_price_index_sql as cells
    else:
        import build_daily_price_index_sql as cells
    raw = []
    section = ""
    headers = 0
    for page_number, page in enumerate(pages, 1):
        for table in page.extract_tables() or []:
            if any(cells._is_table_header(row) for row in table if row):
                headers += 1
            elif not headers:
                continue
            for row_number, row in enumerate(table, 1):
                if not row or cells._is_table_header(row) or cells._is_repeated_header_fragment(row):
                    continue
                # November 2026: commodity spans three physical cells, then
                # specification and price (five cells total).
                if len(row) == 5:
                    commodity, specification, unit, price = (
                        cells._joined(row[:3]), cells._clean(row[3]), "", cells._clean(row[4]))
                else:
                    commodity, specification, unit, price = cells._row_groups(row)
                if not price and commodity and not specification and not unit:
                    heading = commodity.upper()
                    if heading in {"IMPORTED COMMERCIAL", "LOCAL COMMERCIAL"}:
                        section = heading
                    elif heading == "RICE" and section in {"IMPORTED COMMERCIAL", "LOCAL COMMERCIAL"}:
                        section += " RICE"
                    elif heading in cells.SECTION_HEADINGS or heading in {
                        'FISHERIES AND SEAFOOD', 'BEEF', 'BEEF OFFALS', 'BUFFALO',
                        'PORK', 'PORK OFFALS', 'LAMB', 'CHICKEN', 'DUCK',
                        'EGG', 'CHICKEN OFFALS', 'ROOTCROPS',
                    }:
                        section = heading
                    continue
                if not cells.PRICE_RE.fullmatch(price):
                    continue
                # New report headings replace explicit species prefixes.
                # Restore those labels, preserving the original cell in evidence.
                original_commodity = commodity
                prefix = {'BEEF': 'Beef', 'BEEF OFFALS': 'Beef', 'BUFFALO': 'Buffalo',
                          'PORK': 'Pork', 'PORK OFFALS': 'Pork', 'LAMB': 'Lamb',
                          'CHICKEN': 'Chicken', 'CHICKEN OFFALS': 'Chicken', 'DUCK': 'Duck'}.get(section)
                if not raw_only and prefix and not commodity.casefold().startswith(prefix.casefold()):
                    commodity = f'{prefix} {commodity}'
                from decimal import Decimal
                available = bool(re.fullmatch(r"\d[\d,]*(?:\.\d+)?", price))
                numeric = Decimal(price.replace(",", "")) if available else None
                available = numeric is not None and numeric > 0
                raw.append({"section": section, "commodity": commodity,
                            "specification": specification, "reported_commodity": original_commodity,
                            "reported_unit": unit or None,
                            "reported_price": price, "price_index": str(numeric) if available else None,
                            "available": available, "report_date": str(report_date),
                            "source_pdf": url, "page": page_number, "table_row": row_number})
    if raw_only:
        available_rows = [row for row in raw if row['available']]
        if not headers or not available_rows:
            raise RuntimeError('No numeric structured DPI price rows found')
        return available_rows, {
            'raw_price_rows': len(raw),
            'numeric_rows': len(available_rows),
            'not_available_rows': sum(not row['available'] for row in raw),
            'raw_rows': raw,
            'row_contract': 'official_source_cells_not_database_crosswalk',
        }
    rows, stats = cells._map_source_rows(raw)
    if not headers or not rows:
        raise RuntimeError("No supported structured DPI price rows found")
    if stats['unmapped_supported_rows'] or stats['unassigned_source_rows']:
        raise RuntimeError(f"Unresolved supported DPI table rows; refusing a partial parse: {stats['unmapped_supported_rows'][:5]} {stats['unassigned_source_rows'][:5]}")
    seen = {}
    for row in rows:
        identity = tuple(row.get(key) for key in ('product_name', 'product_variant', 'origin', 'unit'))
        if identity in seen:
            raise RuntimeError(f"Duplicate DPI commodity identity: {identity}")
        seen[identity] = row
    stats.update(raw_price_rows=len(raw), not_available_rows=sum(not row['available'] for row in raw))
    return rows, stats


def parse_pdf(url: str, *, deterministic=False, artifact_dir=None, return_metadata=False) -> list[dict]:
    """Parse a DA Daily Price Index PDF, failing closed on the wrong report.

    DPI has one prevailing price per commodity row. DA's older range reports
    can contain the same same-day averages, but are not refreshed consistently;
    this parser validates DPI documents so stale range PDFs are not treated as
    current DPI updates.
    """
    report_date = extract_date_from_url(url)
    if report_date is None:
        raise ValueError(f"Could not determine report date from DA PDF URL: {url}")

    if __package__:
        from .pdf_detector import fetch_official
        from .build_daily_price_index_sql import _embedded_report_date
    else:
        from pdf_detector import fetch_official
        from build_daily_price_index_sql import _embedded_report_date
    response = fetch_official(url)
    if not response.content.startswith(b'%PDF-'):
        raise RuntimeError('Official source response is not a PDF')

    with pdfplumber.open(BytesIO(response.content)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
        if not pages or any(not text.strip() for text in pages):
            raise RuntimeError('PDF has empty or unextractable pages')
        # The first-page report header is authoritative, never a footer or URL.
        printed_date = _embedded_report_date(pages[0])
        if printed_date != report_date:
            raise RuntimeError(f'PDF header date {printed_date} does not match URL date {report_date}')
        if deterministic:
            rows, stats = parse_daily_tables(pdf.pages, printed_date, url, raw_only=True)

    missing_pages = [str(index + 1) for index, text in enumerate(pages) if not text.strip()]
    if missing_pages:
        raise RuntimeError(
            "PDF text extraction missed page(s) " + ", ".join(missing_pages)
        )

    full_text = "\n".join(pages)
    normalized = " ".join(full_text.split()).casefold()
    if "daily price index" not in normalized:
        raise RuntimeError("PDF is not a DA Daily Price Index report")
    if 'prevailing retail price per' not in normalized or 'unit (p/unit)' not in normalized:
        raise RuntimeError("Daily Price Index table header was not found")
    if not _matches_report_date(full_text, report_date):
        raise RuntimeError(
            f"PDF report date does not match its URL date {report_date.isoformat()}"
        )

    if deterministic:
        from pathlib import Path
        from hashlib import sha256
        import json
        metadata = {'source_url': url, 'download_url': getattr(response, 'url', url),
                    'report_date': printed_date.isoformat(), 'row_count': len(rows),
                    'content_bytes': len(response.content), 'content_sha256': sha256(response.content).hexdigest(),
                    'page_count': len(pages), **stats}
        if artifact_dir is not None:
            destination = Path(artifact_dir)
            destination.mkdir(parents=True, exist_ok=True)
            pdf_path = destination / f'{printed_date}.pdf'
            pdf_path.write_bytes(response.content)
            metadata['pdf_path'] = str(pdf_path)
            (destination / f'{printed_date}.json').write_text(
                json.dumps({'metadata': metadata, 'rows': rows}, indent=2), encoding='utf-8')
        return (rows, metadata) if return_metadata else rows
    # Keep AI and its API-key configuration exclusively on the live write path.
    if __package__:
        from .ai_parser import parse_pdf_text_with_ai
    else:
        from ai_parser import parse_pdf_text_with_ai
    table_text = re.split(r"\bNote\(s\):", full_text, maxsplit=1, flags=re.IGNORECASE)[0]
    rows = parse_pdf_text_with_ai(table_text, report_date, url)
    print(f"Parsed {len(rows)} Daily Price Index row(s) via AI")
    return rows
