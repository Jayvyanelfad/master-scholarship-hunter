"""DAAD scholarship-database discovery adapter.

Discovery starts at the official DAAD scholarship database (verified live:
country, programme, subject, and purpose filters with result records). The
adapter follows individual scholarship record pages on daad.de and parses
them with DAAD-aware label normalization, because DAAD pages use headings
such as "Who can apply?" and "What is funded?" rather than the aggregator
vocabulary. Germany is the fixed destination. The database filter country is
the country of residence/applications, which must not be confused with
Beninese nationality.
"""

from __future__ import annotations

import re

from .base import (
    DiscoveryCandidate,
    DetailResult,
    ListingResult,
    SourceAdapter,
    absolutize,
    blank_fields,
    extract_links,
    extract_text,
    extract_title,
    host_in_domains,
)
from ..verification import extract_structured_fields

DAAD_DOMAINS = ("daad.de", "www2.daad.de")
DISCOVERY_URLS = (
    "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/",
    "https://www.daad.de/en/studying-in-germany/scholarships/daad-scholarships/",
)

# DAAD page headings mapped onto the shared structured-field vocabulary so the
# generic extractor can read official DAAD programme pages.
DAAD_LABEL_ALIASES = (
    ("Who can apply?", "Eligible Nationalities:"),
    ("Requirements", "Eligibility criteria:"),
    ("What is funded?", "Funding Type:"),
    ("Value", "Funding Type:"),
    ("Duration of the funding", "Deadline:"),
    ("Application deadline", "Deadline:"),
    ("Selection", "Eligibility criteria:"),
    ("Target group", "Eligible Degrees:"),
)


class DaadAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="daad",
            display_name="DAAD",
            source_type="official_government",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="database_then_record",
            pagination="bounded_listing_links",
            max_pages=8,
            max_records=50,
            official_domains=DAAD_DOMAINS,
            destination="Germany",
            detail_is_official=True,
            enabled=True,
            status_reason="Official scholarship database verified live; individual DAAD record pages are official evidence.",
            notes="Pay special attention to Master's funding for international/developing-country applicants.",
        )

    def is_listing_url(self, url: str) -> bool:
        return host_in_domains(url, DAAD_DOMAINS) and not self.is_detail_url(url)

    def is_detail_url(self, url: str) -> bool:
        if not host_in_domains(url, DAAD_DOMAINS):
            return False
        if url.rstrip("/").lower() in {item.lower().rstrip("/") for item in DISCOVERY_URLS}:
            return False
        lowered = url.lower()
        return any(
            token in lowered
            for token in ("/stipendium/", "/scholarship/", "/scholarships/", "/grant", "/award", "/programme/", "/program/")
        )

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not self.is_detail_url(absolute):
                continue
            canonical = absolute.lower().rstrip("/")
            if canonical in seen:
                continue
            seen.add(canonical)
            found.append(DiscoveryCandidate(url=absolute, title=anchor, context=anchor))
            if len(found) >= self.max_records:
                break
        return ListingResult(candidates=tuple(found))

    def normalize_daad_text(self, text: str) -> str:
        normalized = text
        for source_label, target_label in DAAD_LABEL_ALIASES:
            normalized = re.sub(re.escape(source_label), target_label, normalized, flags=re.I)
        return normalized

    def parse_detail(self, html: str, url: str) -> DetailResult:
        fields = extract_structured_fields(self.normalize_daad_text(extract_text(html)))
        if not fields["destination"]:
            fields["destination"] = self.destination
        return DetailResult(title=extract_title(html), fields=fields or blank_fields())
