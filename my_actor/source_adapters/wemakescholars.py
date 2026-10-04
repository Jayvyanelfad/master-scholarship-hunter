"""WeMakeScholars discovery adapter (reputable aggregator, not evidence).

Listing pages lead to individual scholarship detail pages; detail pages are
parsed for structured fields and for one explicitly labelled official or
application link. The official hop itself stays in ``my_actor.routes`` so the
shared safety checks apply. Aggregator evidence never overrides official
evidence.
"""

from __future__ import annotations

from urllib.parse import urlparse

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
    is_junk_page,
)
from ..verification import extract_structured_fields

WMS_DOMAINS = ("www.wemakescholars.com", "wemakescholars.com", "zeta.wemakescholars.com")
SCHOLARSHIP_PATH_MARKERS = ("/scholarship/", "/scholarships/")
# Index/filter pages that list scholarships but are not individual records.
# Observed live: /university/<slug>/scholarships and
# /scholarships-to-study-in-<country>-for-international-students are
# server-rendered indexes; individual cards on the main listing are
# AJAX-loaded, so only /scholarship/<slug> pages are real details.
INDEX_PATH_HINTS = ("/university/", "scholarships-to-study-in-")


def is_wms(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in WMS_DOMAINS


def is_scholarship_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not is_wms(url):
        return False
    path = parsed.path.lower()
    if not any(marker in path for marker in SCHOLARSHIP_PATH_MARKERS):
        return False
    if path.rstrip("/") in ("/scholarship", "/scholarships"):
        return False
    return not any(hint in path for hint in INDEX_PATH_HINTS)


class WeMakeScholarsAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="wemakescholars",
            display_name="WeMakeScholars",
            source_type="reputable_aggregator",
            discovery_urls=(
                "https://www.wemakescholars.com/Masters-scholarships-in-computer-sciences-and-information-technology-to-study-abroad",
                # Server-rendered filtered search behind the listing page
                # (its own inline script references this endpoint).
                "https://www.wemakescholars.com/scholarship?study=3&interest=3",
            ),
            discovery_strategy="listing_then_detail",
            pagination="bounded_listing_links",
            max_pages=10,
            max_records=50,
            official_domains=WMS_DOMAINS,
            destination="",
            detail_is_official=False,
            enabled=True,
            status_reason="Discovery adapter implemented; strong matches still require official evidence.",
            notes="Discovery source only. Never official evidence.",
        )

    def is_listing_url(self, url: str) -> bool:
        return is_wms(url) and not is_scholarship_url(url)

    def is_detail_url(self, url: str) -> bool:
        return is_scholarship_url(url)

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not is_scholarship_url(absolute):
                continue
            canonical = absolute.rstrip("/")
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
        fields = extract_structured_fields(extract_text(html))
        return DetailResult(title=extract_title(html), fields=fields or blank_fields())
