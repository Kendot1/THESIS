"""Point-in-time research access to reviewed rice import-price benchmarks.

This adapter admits numerically reviewed and independently dated records to
research lookups only. It does not equate customs grades to Foodcast grades or
enable a model feature in production. Age limits are explicit at every lookup.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from types import MappingProxyType


@dataclass(frozen=True)
class ReferenceQuote:
    record_id: str
    grade: str
    country: str
    reference_start: date
    reference_end: date
    available_at: datetime
    value: float | None
    missing_reason: str | None
    artifact_sha256: str
    source_url: str


def join_reviewed_availability(reviewed, availability):
    """Join checked build outputs by original PDF hash and URL; fail closed.

    Callers must verify original source and evidence manifests with the builders
    before providing these outputs. This function is not a signature verifier.
    """
    if reviewed["capture_manifest_sha256"] != availability["source_capture_sha256"]:
        raise ValueError("Reviewed rows and archive evidence use different captures")
    indexed = {}
    for record in availability["records"]:
        key = (record["artifact_sha256"], record["source_url"])
        if key in indexed:
            raise ValueError("Duplicate availability record")
        indexed[key] = record
    quotes = []
    excluded = []
    seen = set()
    for row in reviewed["records"]:
        if row["record_id"] in seen:
            raise ValueError("Duplicate reviewed row")
        seen.add(row["record_id"])
        evidence = indexed.get((row["artifact_sha256"], row["source_url"]))
        if row.get("numeric_visual_reviewed") is not True or not evidence or evidence.get("historical_availability_verified") is not True:
            excluded.append({"record_id": row["record_id"], "reason": "numeric_or_historical_availability_unverified"})
            continue
        available = datetime.fromisoformat(evidence["available_at_utc"])
        capture = datetime.fromisoformat(row["captured_at_utc"])
        if available.tzinfo is None or available.utcoffset() is None or capture.tzinfo is None:
            raise ValueError("Availability and capture timestamps require timezones")
        if available > capture:
            raise ValueError("Historical availability cannot follow source retrieval")
        start, end = date.fromisoformat(row["reference_start"]), date.fromisoformat(row["reference_end"])
        if start > end:
            raise ValueError("Reversed reference period")
        value = row["value"]
        if row["unit"] != "USD/kg" or (value is not None and (isinstance(value, bool) or not math.isfinite(value) or value <= 0)):
            raise ValueError("Invalid reviewed value or unit")
        if value is None and row.get("missing_reason") != "source_reports_NA":
            raise ValueError("Unexplained missing source value")
        quotes.append(ReferenceQuote(row["record_id"], row["grade_literal"], row["country_code_literal"],
                                     start, end, available, value, row.get("missing_reason"),
                                     row["artifact_sha256"], row["source_url"]))
    return tuple(quotes), excluded


class QuoteArchive:
    def __init__(self, quotes):
        self.quotes = tuple(quotes)
        keys = [(q.grade, q.country, q.reference_start, q.available_at) for q in self.quotes]
        if len(keys) != len(set(keys)):
            raise ValueError("Ambiguous benchmark vintage")

    def at(self, origin, *, grade, country, lag_days, max_age_days):
        if origin.tzinfo is None or origin.utcoffset() is None:
            raise ValueError("Origin requires timezone")
        if type(lag_days) is not int or type(max_age_days) is not int or lag_days < 0 or max_age_days < 0:
            raise ValueError("Lag and maximum age must be nonnegative integer days")
        cutoff = origin - timedelta(days=lag_days)
        eligible = [q for q in self.quotes if q.grade == grade and q.country == country and q.available_at <= cutoff
                    and q.reference_start <= cutoff.date()]
        selected = max(eligible, key=lambda q: (q.reference_start, q.available_at), default=None)
        result = {"value": None, "missing": 1, "reference_age_days": None, "availability_age_days": None,
                  "record_id": None, "reason": "no_available_quote", "lag_days": lag_days,
                  "max_age_days": max_age_days, "unit": "USD/kg"}
        if selected:
            # Measure age at the actual forecast, not at the shifted cutoff.
            # Changing a lag must never make an old price appear fresher.
            reference_age = (origin.date() - selected.reference_start).days
            result.update(reference_age_days=reference_age,
                          availability_age_days=(origin - selected.available_at).total_seconds() / 86400,
                          record_id=selected.record_id)
            if reference_age > max_age_days:
                result["reason"] = "stale_reference"
            elif selected.value is None:
                result["reason"] = selected.missing_reason
            else:
                result.update(value=selected.value, missing=0, reason="available_reviewed_quote")
        return MappingProxyType(result)
