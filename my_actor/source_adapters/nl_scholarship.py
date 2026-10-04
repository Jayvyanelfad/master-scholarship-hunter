"""Netherlands NL Scholarship adapter (partial-award control case).

The official Study in NL page (verified live) states the award amounts to
EUR 5,000 in the first year and explicitly that "this is not a full-tuition
scholarship". This adapter exists precisely to prove that discovery and
eligibility filtering are separate concerns: the scholarship is discovered,
parsed correctly (non-EEA nationality, bachelor's or master's, Netherlands
destination), and then rejected by the strict funding verifier. If this
source ever yields a strong_match, the funding rules have regressed.
"""

from __future__ import annotations

from .base import (
    DetailResult,
    ListingResult,
    SourceAdapter,
    blank_fields,
    extract_text,
    extract_title,
    host_in_domains,
    is_junk_page,
)
from ..verification import extract_structured_fields

NL_DOMAINS = ("studyinnl.org", "www.studyinnl.org", "nuffic.nl", "www.nuffic.nl")
DISCOVERY_URLS = (
    "https://www.studyinnl.org/finances/nl-scholarship",
)


class NlScholarshipAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="nl_scholarship",
            display_name="Study in NL",
            source_type="official_government",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="single_call_page",
            pagination="none",
            max_pages=2,
            max_records=5,
            official_domains=NL_DOMAINS,
            destination="Netherlands",
            detail_is_official=True,
            enabled=True,
            status_reason="Official NL Scholarship page verified live; EUR 5,000 non-full-tuition award used as the partial-funding control case.",
            notes="Must be rejected for this profile: EUR 5,000 is not full funding.",
        )

    def is_listing_url(self, url: str) -> bool:
        return False

    def is_detail_url(self, url: str) -> bool:
        return host_in_domains(url, NL_DOMAINS) and "nl-scholarship" in url.lower()

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        return ListingResult()

    def parse_detail(self, html: str, url: str) -> DetailResult:
        junk = is_junk_page(html, url)
        if junk:
            return DetailResult(title=extract_title(html), fields=blank_fields(), skip=True, skip_reason=junk)
        fields = extract_structured_fields(extract_text(html))
        if not fields["destination"]:
            fields["destination"] = self.destination
        return DetailResult(title=extract_title(html), fields=fields or blank_fields())
