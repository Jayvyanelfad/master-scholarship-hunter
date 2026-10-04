"""DAAD scholarship-database discovery adapter.

Discovery starts at the official DAAD scholarship database (verified live:
country, programme, subject, and purpose filters with result records). The
adapter follows individual scholarship record pages on daad.de and parses
them with DAAD-aware label normalization, because DAAD pages use headings
such as "Who can apply?" and "What is funded?" rather than the aggregator
vocabulary. Germany is the fixed destination. The database filter country is
the country of residence/applications, which must not be confused with
Beninese nationality.

Record hygiene (from production evidence): only actual scholarship or
programme records become candidates. Cookie, FAQ, accessibility, press, and
generic landing pages are navigation, never records.
"""

from __future__ import annotations

import re

from urllib.parse import urlparse

from .base import (
    DiscoveryCandidate,
    DetailResult,
    ListingResult,
    SourceAdapter,
    absolutize,
    blank_fields,
    canonical_programme_url,
    extract_evidence_sentences,
    extract_links,
    extract_text,
    extract_title,
    host_in_domains,
    is_generic_info_page,
    is_junk_page,
)
from ..verification import extract_structured_fields

DAAD_DOMAINS = ("daad.de", "www2.daad.de")
DISCOVERY_URLS = (
    "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/",
    "https://www.daad.de/en/studying-in-germany/scholarships/daad-scholarships/",
)

# URL tokens of utility/navigation pages that are never scholarship records
# (matched per path segment in _is_navigation_url, never as bare substrings).
# Scholarship-record URL markers on DAAD domains.
RECORD_PATH_TOKENS = (
    "/stipendium/", "/scholarship/", "/scholarships/", "/grant", "/award",
    "/programme/", "/program/", "/funding/",
)
GENERIC_LANDING_SLUGS = (
    "scholarships", "scholarship-database", "daad-scholarships", "funding",
    "scholarships-funding",
)

FUNDING_PROSE_KEYWORDS = (
    "funded", "tuition", "monthly", "stipend", "living", "allowance",
    "travel", "insurance", "grant covers", "what is funded", "value",
)
NATIONALITY_PROSE_KEYWORDS = (
    "who can apply", "target group", "eligible", "applicants from",
    "graduates from", "countries", "nationals", "international",
)
APPLY_PROSE_KEYWORDS = (
    "apply from abroad", "international applicants", "application portal",
    "apply via", "applications must be submitted", "how to apply",
)
DEADLINE_PROSE_KEYWORDS = ("deadline", "closing date", "application deadline", "call for applications")

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

    def _is_navigation_url(self, url: str) -> bool:
        # Segment-exact matching: bare substrings such as "search" would
        # falsely match "/study-and-research-in-germany/".
        segments = [part for part in urlparse(url).path.lower().split("/") if part]
        short_tokens = {
            "faq", "hilfe", "help", "kontakt", "contact", "suche", "search",
            "news", "press", "presse", "events",
        }
        if any(segment in short_tokens for segment in segments):
            return True
        if any(segment.startswith("cookie") for segment in segments):
            return True
        lowered = url.lower()
        if any(
            token in lowered
            for token in (
                "impressum", "imprint", "datenschutz", "data-protection",
                "accessibility", "barrierefreiheit", "newsletter",
                "veranstaltung", "sitemap",
            )
        ):
            return True
        slug = segments[-1] if segments else ""
        return slug in GENERIC_LANDING_SLUGS

    def is_listing_url(self, url: str) -> bool:
        return host_in_domains(url, DAAD_DOMAINS) and not self.is_detail_url(url)

    def is_detail_url(self, url: str) -> bool:
        if not host_in_domains(url, DAAD_DOMAINS):
            return False
        if url.rstrip("/").lower() in {item.lower().rstrip("/") for item in DISCOVERY_URLS}:
            return False
        lowered = url.lower()
        if self._is_navigation_url(url):
            return False
        if "datenbank" in lowered:
            # The scholarship database (including filtered variants) is a
            # search interface, never a scholarship record.
            return False
        return any(token in lowered for token in RECORD_PATH_TOKENS)

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        from .base import matches_nav_anchor

        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not self.is_detail_url(absolute):
                continue
            if matches_nav_anchor(anchor):
                continue
            identity = canonical_programme_url(absolute)
            if identity in seen:
                continue
            seen.add(identity)
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
        junk = is_junk_page(html, url)
        if junk:
            return DetailResult(title=extract_title(html), fields=blank_fields(), skip=True, skip_reason=junk)
        text = extract_text(html)
        fields = extract_structured_fields(self.normalize_daad_text(text))
        if not fields["destination"]:
            fields["destination"] = self.destination
        if not fields["funding"]:
            fields["funding"] = extract_evidence_sentences(text, FUNDING_PROSE_KEYWORDS)
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, NATIONALITY_PROSE_KEYWORDS)
        if not fields["application_location"]:
            fields["application_location"] = extract_evidence_sentences(text, APPLY_PROSE_KEYWORDS)
        if not fields["deadline"]:
            fields["deadline"] = extract_evidence_sentences(text, DEADLINE_PROSE_KEYWORDS)
        title = extract_title(html)
        generic = is_generic_info_page(title, fields)
        if generic:
            return DetailResult(title=title, fields=blank_fields(), skip=True, skip_reason=generic)
        return DetailResult(title=title, fields=fields or blank_fields())
