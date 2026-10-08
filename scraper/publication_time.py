"""Extract publication timing without inventing historical availability."""
from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
import re
from typing import Any


def _iso_metadata(raw: Any) -> dict[str, str | None] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None

    if parsed.tzinfo is not None and ("T" in value or " " in value):
        return {"published_at": parsed.isoformat(), "published_date": parsed.date().isoformat(),
                "publication_precision": "timestamp"}
    return {"published_at": None, "published_date": parsed.date().isoformat(),
            "publication_precision": "date"}


def publication_metadata(metadata: dict | None, html: str | None, url: str | None) -> dict:
    """Return source timing fields; date-only evidence never becomes midnight UTC."""
    candidates: list[tuple[Any, str]] = []
    metadata = metadata or {}
    if metadata.get("published_at"):
        candidates.append((metadata["published_at"], "crawler_metadata"))

    if html:
        for pattern, source in (
            (r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
             "article_published_meta"),
            (r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time',
             "article_published_meta"),
            (r'"datePublished"\s*:\s*"([^"]+)"', "json_ld_date_published"),
        ):
            match = re.search(pattern, html, re.I)
            if match:
                candidates.append((match.group(1), source))

    if url:
        match = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
        if match:
            year, month, day = (int(part) for part in match.groups())
            try:
                candidates.append((date(year, month, day).isoformat(), "url_date"))
            except ValueError:
                pass

    for raw, source in candidates:
        parsed = _iso_metadata(raw)
        if parsed is not None:
            return {**parsed, "publication_source": source}

    return {"published_at": None, "published_date": None,
            "publication_precision": "unknown", "publication_source": "unknown"}
