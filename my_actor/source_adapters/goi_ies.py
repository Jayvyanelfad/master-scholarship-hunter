"""Government of Ireland International Education Scholarship adapter.

Single official programme page (verified live on hea.ie). Verified facts:

- NFQ levels 9/10: Master's, postgraduate diploma, or PhD at an eligible
  Irish institution. Doctoral-only readings must not become Master's claims;
  the adapter keeps the raw degree wording so the matcher sees it.
- Benefits: a EUR 10,000 stipend for one year plus a full fee waiver from the
  host institution. Whether that satisfies full funding is decided by the
  strict funding verifier from this evidence, never from the word
  "scholarship".
- Eligibility: domiciliary of origin outside the EU/EEA, Switzerland, and the
  UK. Russian and Belarusian nationals are excluded. A Beninese applicant
  passes; the exclusion list does not touch Benin.
- Calls close (the 2026 call closed 12 March 2026). Only a current call with
  a live deadline can qualify; between-cycle pages stay non-strong.
"""

from __future__ import annotations

from .base import (
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

GOI_DOMAINS = ("hea.ie", "www.hea.ie")
DISCOVERY_URLS = (
    "https://hea.ie/policy/internationalisation/goi-ies/",
)


class GoiIesAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="goi_ies",
            display_name="Government of Ireland",
            source_type="official_government",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="single_call_page",
            pagination="none",
            max_pages=2,
            max_records=5,
            official_domains=GOI_DOMAINS,
            destination="Ireland",
            detail_is_official=True,
            enabled=True,
            status_reason="Official GOI-IES call page verified live with benefits, eligibility, and deadline wording.",
            notes="EUR 10,000 stipend plus fee waiver is evidence; the funding verifier decides full funding.",
        )

    def is_listing_url(self, url: str) -> bool:
        return False

    def is_detail_url(self, url: str) -> bool:
        return host_in_domains(url, GOI_DOMAINS) and "goi-ies" in url.lower()

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        return ListingResult()

    def parse_detail(self, html: str, url: str) -> DetailResult:
        junk = is_junk_page(html, url)
        if junk:
            return DetailResult(title=extract_title(html), fields=blank_fields(), skip=True, skip_reason=junk)
        text = extract_text(html)
        fields = extract_structured_fields(text)
        if not fields["destination"]:
            fields["destination"] = self.destination
        if not fields["funding"]:
            fields["funding"] = extract_evidence_sentences(text, (
                "stipend", "fee waiver", "tuition", "living", "allowance",
            ))
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, (
                "domiciliary", "outside the eu", "eligible", "nationals",
                "international students",
            ))
        return DetailResult(title=extract_title(html), fields=fields or blank_fields())
