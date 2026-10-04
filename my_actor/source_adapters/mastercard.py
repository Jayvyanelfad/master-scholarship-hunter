"""Mastercard Foundation Scholars Program adapter (partner-university model).

The Foundation homepage is NOT a scholarship application page: applications
are managed by partner universities, each with its own programmes, deadlines,
and guidelines (verified live in the official FAQ). The adapter therefore
works in two stages:

1. The Foundation programme/FAQ pages provide framework evidence
   (Master's supported, PhD not supported; tuition/accommodation/books/air
   ticket coverage; African youth focus; per-partner deadlines).
2. Partner-institution links explicitly presented as application routes
   ("Where to apply", partner universities) are followed as official
   follow-ups. Each partner page is evaluated on its own evidence for
   degree, field, African/Benin eligibility, benefits, deadline, and route.

Old partner lists are never treated as current eligibility: every partner
opportunity must be verified on the partner's current official page.
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
    extract_evidence_sentences,
    extract_links,
    extract_text,
    extract_title,
    host_in_domains,
    is_junk_page,
)
from ..verification import extract_structured_fields

FOUNDATION_DOMAINS = ("mastercardfdn.org", "www.mastercardfdn.org")
DISCOVERY_URLS = (
    "https://mastercardfdn.org/en/what-we-do/our-programs/mastercard-foundation-scholars-program/",
    "https://mastercardfdn.org/en/frequently-asked-questions/",
)

PARTNER_ANCHOR_HINTS = ("where to apply", "partner universit", "apply through", "affiliated institution", "find an institution")
PARTNER_PATH_HINTS = ("partner", "universit", "scholar", "apply", "admission")


class MastercardAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="mastercard_foundation",
            display_name="Mastercard Foundation Scholars Program",
            source_type="official_program",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="framework_then_partners",
            pagination="bounded_listing_links",
            max_pages=6,
            max_records=40,
            official_domains=FOUNDATION_DOMAINS,
            destination="",
            detail_is_official=True,
            enabled=True,
            status_reason="Official programme and FAQ pages verified live; partner-university application model confirmed in FAQ.",
            notes="Focus on current Master's opportunities for African applicants; verify each partner page.",
        )

    def is_listing_url(self, url: str) -> bool:
        return host_in_domains(url, FOUNDATION_DOMAINS) and not self.is_detail_url(url)

    def is_detail_url(self, url: str) -> bool:
        # Partner university pages live on external official university domains
        # after being explicitly linked as application routes; they are matched
        # at runtime by the follow-up policy, not by a static domain list.
        return host_in_domains(url, FOUNDATION_DOMAINS) and any(
            hint in url.lower() for hint in ("scholar", "partner", "faq", "universit")
        )

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        from .base import matches_nav_anchor

        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            anchor_lower = anchor.lower()
            if matches_nav_anchor(anchor):
                continue
            if not any(hint in anchor_lower for hint in PARTNER_ANCHOR_HINTS) and not self.is_detail_url(absolute):
                continue
            canonical = absolute.lower().rstrip("/")
            if canonical in seen:
                continue
            seen.add(canonical)
            found.append(DiscoveryCandidate(url=absolute, title=anchor, context=anchor))
            if len(found) >= self.max_records:
                break
        return ListingResult(candidates=tuple(found))

    def is_partner_followup(self, url: str, anchor_text: str) -> bool:
        """Decide whether an outbound link is a genuine partner route.

        Foundation-domain links always stay in-adapter. External links qualify
        only with an explicit partner/application anchor; bare "read more" or
        news links never qualify.
        """
        if host_in_domains(url, FOUNDATION_DOMAINS):
            return True
        anchor_lower = (anchor_text or "").lower()
        return any(hint in anchor_lower for hint in PARTNER_ANCHOR_HINTS)

    def parse_detail(self, html: str, url: str) -> DetailResult:
        junk = is_junk_page(html, url)
        if junk:
            return DetailResult(title=extract_title(html), fields=blank_fields(), skip=True, skip_reason=junk)
        text = extract_text(html)
        fields = extract_structured_fields(text)
        if not fields["funding"]:
            fields["funding"] = extract_evidence_sentences(text, (
                "tuition fees", "accommodation", "stipend", "financial support",
                "air ticket", "books",
            ))
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, (
                "african", "young people", "eligible", "apply through",
            ))
        follow: list[str] = []
        if host_in_domains(url, FOUNDATION_DOMAINS):
            for href, anchor in extract_links(html):
                absolute = absolutize(url, href)
                if not absolute.lower().startswith(("http://", "https://")):
                    continue
                if absolute.lower().rstrip("/") == url.lower().rstrip("/"):
                    continue
                if self.is_partner_followup(absolute, anchor):
                    if absolute not in follow:
                        follow.append(absolute)
                    if len(follow) >= 15:
                        break
        return DetailResult(
            title=extract_title(html),
            fields=fields or blank_fields(),
            follow_links=tuple(follow),
        )
