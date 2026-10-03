"""Erasmus Mundus Joint Masters discovery adapter.

The Erasmus overview page is a discovery surface, never the scholarship
itself: it links to the course catalogue and to individual EMJM programme
pages. Programme pages explicitly linked from this official source become the
primary evidence (official programme pages). Verified facts encoded from the
official page: full scholarships exist for the best-ranked students worldwide
and cover participation costs plus travel, visa, and a living allowance;
programmes last 1-2 academic years; applications typically run October-January
via each programme's own site.
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
from ..verification import LinkCandidate, extract_structured_fields, select_official_url

ERASMUS_DOMAINS = ("erasmus-plus.ec.europa.eu", "europa.eu", "eacea.ec.europa.eu")
DISCOVERY_URLS = (
    "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters",
)
CATALOGUE_HINTS = ("catalogue", "catalog", "search", "course", "programme", "program", "master", "emjm", "emjmd")


class ErasmusMundusAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="erasmus_mundus",
            display_name="Erasmus Mundus",
            source_type="official_program",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="overview_then_catalogue_then_programme",
            pagination="bounded_listing_links",
            max_pages=8,
            max_records=50,
            official_domains=ERASMUS_DOMAINS,
            destination="",
            detail_is_official=True,
            enabled=True,
            status_reason="Official discovery surface verified live; programme pages explicitly linked from it are official programme evidence.",
            notes="Verify Master's, field, participating countries, benefits, deadline, and nationality per programme.",
        )

    def is_listing_url(self, url: str) -> bool:
        if url.rstrip("/").lower() in {item.lower() for item in DISCOVERY_URLS}:
            return True
        return host_in_domains(url, ERASMUS_DOMAINS) and any(
            hint in url.lower() for hint in ("catalogue", "catalog", "opportunit", "programme", "program", "master")
        ) and not self.is_detail_url(url)

    def is_detail_url(self, url: str) -> bool:
        lowered = url.lower()
        if lowered.rstrip("/") in {item.lower() for item in DISCOVERY_URLS}:
            return False
        # Individual consortium programme pages live on university domains after
        # being explicitly linked from the official catalogue/overview.
        return any(hint in lowered for hint in ("master", "mundus", "emjm", "emjmd", "msc", "programme", "program"))

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            lowered = absolute.lower()
            anchor_lower = anchor.lower()
            looks_like_programme = any(hint in lowered for hint in CATALOGUE_HINTS) or any(
                hint in anchor_lower for hint in ("master", "programme", "catalogue", "apply", "course")
            )
            if not looks_like_programme:
                continue
            canonical = lowered.rstrip("/")
            if canonical in seen or canonical in {item.lower() for item in DISCOVERY_URLS}:
                continue
            seen.add(canonical)
            found.append(DiscoveryCandidate(url=absolute, title=anchor, context=anchor))
            if len(found) >= self.max_records:
                break
        return ListingResult(candidates=tuple(found))

    def parse_detail(self, html: str, url: str) -> DetailResult:
        text = extract_text(html)
        fields = extract_structured_fields(text)
        follow: list[str] = []
        if host_in_domains(url, ERASMUS_DOMAINS):
            # Still on an official index/catalogue page: resolve the actual
            # programme/application page instead of treating this as evidence.
            candidates = [
                LinkCandidate(absolutize(url, href), anchor)
                for href, anchor in extract_links(html)
            ]
            official = select_official_url(url, extract_title(html), candidates)
            if official and official.lower().rstrip("/") != url.lower().rstrip("/"):
                follow.append(official)
        return DetailResult(
            title=extract_title(html),
            fields=fields or blank_fields(),
            follow_links=tuple(follow),
            is_hop=bool(follow),
        )
