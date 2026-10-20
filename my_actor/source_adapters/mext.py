"""MEXT (Japanese Government) scholarship adapter.

Discovery starts at the official Study in Japan MEXT page (verified live),
which describes seven scholarship types. Only the "Research students"
pathway can lead to Master's admission, and even it is shared with doctoral
applicants, so the adapter is strict about degree wording:

- "eligible for admission to a master's program" is Master's evidence.
- Undergraduate, teacher-training, and other types are never Master's.
- A page that only says "doctoral" or "research student" without Master's
  wording stays unknown, never eligible.

Verified facts: under-35 age rule for research students; monthly stipend
(JPY 143,000-145,000 scale); tuition exemption; round-trip airfare; embassy
or university recommendation routes. Nationality wording on the overview page
does not name eligible countries, so records stay nationality-unknown until
a country-specific guideline page is verified. Always confirm the latest
official guideline; never reuse stale cycles.
"""

from __future__ import annotations

from .base import (
    fill_prose_evidence,
    DetailResult,
    ListingResult,
    SourceAdapter,
    blank_fields,
    extract_evidence_sentences,
    extract_text,
    extract_title,
    host_in_domains,
    is_junk_page,
)
from ..verification import extract_structured_fields

MEXT_DOMAINS = ("studyinjapan.go.jp", "www.studyinjapan.go.jp", "mext.go.jp", "www.mext.go.jp")
DISCOVERY_URLS = (
    "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/",
)

RESEARCH_PATHWAY_MARKERS = ("research student", "graduate school level")


class MextAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="mext",
            display_name="MEXT",
            source_type="official_government",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="overview_then_guideline",
            pagination="bounded_listing_links",
            max_pages=4,
            max_records=10,
            official_domains=MEXT_DOMAINS,
            destination="Japan",
            detail_is_official=True,
            enabled=True,
            status_reason="Official MEXT overview verified live with type table, stipend, tuition, travel, and route wording.",
            notes="Distinguish Master's pathway from doctoral/undergraduate; use the latest guideline.",
        )

    def is_listing_url(self, url: str) -> bool:
        return url.rstrip("/").lower() in {item.lower().rstrip("/") for item in DISCOVERY_URLS}

    def is_detail_url(self, url: str) -> bool:
        if not host_in_domains(url, MEXT_DOMAINS):
            return False
        if self.is_listing_url(url):
            return False
        lowered = url.lower()
        return "mext" in lowered or "scholarship" in lowered or "guideline" in lowered

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        # The overview page itself is evaluated as the research-student
        # pathway record; deeper guideline links are followed at runtime only
        # when they match is_detail_url.
        from .base import DiscoveryCandidate, absolutize, extract_links

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

    def parse_detail(self, html: str, url: str) -> DetailResult:
        junk = is_junk_page(html, url)
        if junk:
            return DetailResult(title=extract_title(html), fields=blank_fields(), skip=True, skip_reason=junk)
        text = extract_text(html)
        fields = extract_structured_fields(text)
        fields = fill_prose_evidence(fields, text, extract_title(html))
        if not fields["destination"]:
            fields["destination"] = self.destination
        if not fields["funding"]:
            fields["funding"] = extract_evidence_sentences(text, (
                "per month", "stipend", "tuition", "exempted", "airfare",
                "travel expenses", "scholarship",
            ))
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, (
                "embassy recommendation", "university recommendation",
                "eligible countries", "who can apply", "applicants from",
            ))
        return DetailResult(title=extract_title(html), fields=fields or blank_fields())
