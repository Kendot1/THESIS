"""Point-in-time lookup for reviewed external observation vintages.

An observation period is not a publication timestamp. Callers must retain the
original source artifact and establish when that exact vintage was available.
Unverified archival dates are excluded by default. Experimental opt-in is only
for conditional diagnostics, never production fitting or promotion evidence.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re
from typing import Mapping, Sequence
from urllib.parse import urlparse


@dataclass(frozen=True)
class ObservationRelease:
    reference_end: date
    available_at: datetime
    features: Mapping[str, float | None]
    source_url: str
    artifact_sha256: str
    availability_verified: bool
    availability_evidence: str

    def __post_init__(self):
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("available_at requires an explicit time zone")
        if self.reference_end > self.available_at.date():
            raise ValueError("Observed data cannot precede its reference period")
        if not re.fullmatch(r"[0-9a-f]{64}", self.artifact_sha256):
            raise ValueError("A SHA256 of the exact source artifact is required")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("An HTTPS source URL is required")
        if not self.availability_evidence.strip():
            raise ValueError("Availability evidence or its limitation is required")
        if type(self.availability_verified) is not bool:
            raise ValueError("availability_verified must be boolean")
        if not self.features or any(not isinstance(key, str) or not key for key in self.features):
            raise ValueError("Nonempty named features are required")
        if any(value is not None and (isinstance(value, bool) or not math.isfinite(value))
               for value in self.features.values()):
            raise ValueError("Features must be finite numbers or explicit missing values")
        # Snapshot caller-owned mappings so mutation cannot alter the vintage.
        from types import MappingProxyType
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


class ObservationArchive:
    def __init__(self, releases: Sequence[ObservationRelease]):
        self.releases = tuple(releases)
        keys = [(r.reference_end, r.available_at) for r in self.releases]
        if len(keys) != len(set(keys)):
            raise ValueError("Ambiguous vintages share a period and availability timestamp")

    def at(self, origin: datetime, *, max_age: timedelta,
           allow_unverified_for_diagnostics: bool = False) -> ObservationRelease | None:
        """Latest observation period, then its latest known revision, at origin.

        Missing values remain missing. Staleness is measured from reference end,
        not upload time: a newly uploaded old report does not refresh the data.
        Calendar-day ages use each release's declared local timezone.
        """
        if origin.tzinfo is None or origin.utcoffset() is None:
            raise ValueError("Forecast origin requires an explicit time zone")
        if max_age < timedelta(0):
            raise ValueError("max_age must be nonnegative")
        eligible = [r for r in self.releases
                    if r.available_at <= origin
                    and (r.availability_verified or allow_unverified_for_diagnostics)
                    and timedelta(0) <= origin.astimezone(r.available_at.tzinfo).date()
                    - r.reference_end <= max_age]
        return max(eligible, key=lambda r: (r.reference_end, r.available_at), default=None)
