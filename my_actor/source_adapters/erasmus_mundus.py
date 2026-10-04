"""Erasmus Mundus Joint Masters discovery adapter.

The Erasmus overview page is a discovery surface, never the scholarship
itself: it links to the course catalogue and to individual EMJM programme
pages. Programme pages explicitly linked from this official source become the
primary evidence (official programme pages). Verified facts encoded from the
official page: full scholarships exist for the best-ranked students worldwide
and cover participation costs plus travel, visa, and a living allowance;
programmes last 1-2 academic years; applications typically run October-January
via each programme's own site.

Listing hygiene (from production evidence): the overview page is full of
language-alternate links, social links, and catalogue navigation. Only links
that look like individual programme records become candidates; language
variants of one programme collapse to a single candidate.
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
    canonical_programme_url,
    extract_evidence_sentences,
    extract_links,
    extract_text,
    extract_title,
    host_in_domains,
    is_generic_info_page,
    is_junk_page,
)
from ..verification import LinkCandidate, canonical_url, extract_structured_fields, select_official_url

ERASMUS_DOMAINS = ("erasmus-plus.ec.europa.eu", "europa.eu", "eacea.ec.europa.eu")
DISCOVERY_URLS = (
    "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters",
)
CATALOGUE_HINTS = ("catalogue", "catalog", "search", "course", "programme", "program", "master", "emjm", "emjmd")
# Links that are navigation/localization/social, never programme records.
IGNORED_LINK_HINTS = (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "youtube.com",
    "/language", "select-language", "choose-language", "setlang",
    "cookie", "privacy", "/news", "/events", "/contact", "give your feedback",
)
IGNORED_ANCHOR_HINTS = (
    "facebook", "instagram", "linkedin", "twitter", "youtube", "follow us",
    "select your language", "choose your language", "skip to",
    "give your feedback", "did you find this page useful",
)

FUNDING_PROSE_KEYWORDS = (
    "participation costs", "tuition", "living allowance", "monthly allowance",
    "stipend", "travel", "visa", "insurance", "scholarship cover",
)
NATIONALITY_PROSE_KEYWORDS = (
    "all over the world", "worldwide", "all countries", "all nationalities",
    "international students", "international applicants", "eligible countries",
    "who can apply", "open to",
)
APPLY_PROSE_KEYWORDS = (
    "apply directly", "apply from abroad", "international applicants",
    "application portal", "how to apply", "submit your application",
)
DEADLINE_PROSE_KEYWORDS = ("deadline", "apply between", "closing date", "call for applications")


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

    def _ignored(self, absolute: str, anchor: str) -> bool:
        lowered_url, lowered_anchor = absolute.lower(), anchor.lower()
        if any(hint in lowered_url for hint in IGNORED_LINK_HINTS):
            return True
        if any(hint in lowered_anchor for hint in IGNORED_ANCHOR_HINTS):
            return True
        if lowered_url.rstrip("/") in {item.lower() for item in DISCOVERY_URLS}:
            return True
        return False

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        from .base import matches_nav_anchor

        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            if self._ignored(absolute, anchor):
                continue
            if matches_nav_anchor(anchor):
                continue
            lowered = absolute.lower()
            anchor_lower = anchor.lower()
            looks_like_programme = any(hint in lowered for hint in CATALOGUE_HINTS) or any(
                hint in anchor_lower for hint in ("master", "programme", "catalogue", "apply", "course")
            )
            if not looks_like_programme:
                continue
            identity = canonical_programme_url(absolute)
            if identity in seen:
                continue
            seen.add(identity)
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
        if not fields["funding"]:
            fields["funding"] = extract_evidence_sentences(text, FUNDING_PROSE_KEYWORDS)
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, NATIONALITY_PROSE_KEYWORDS)
        if not fields["application_location"]:
            fields["application_location"] = extract_evidence_sentences(text, APPLY_PROSE_KEYWORDS)
        if not fields["deadline"]:
            fields["deadline"] = extract_evidence_sentences(text, DEADLINE_PROSE_KEYWORDS)
        follow: list[str] = []
        if host_in_domains(url, ERASMUS_DOMAINS):
            # Still on an official index/catalogue page: resolve the actual
            # programme/application page instead of treating this as evidence.
            candidates = [
                LinkCandidate(absolutize(url, href), anchor)
                for href, anchor in extract_links(html)
                if not self._ignored(absolutize(url, href), anchor)
            ]
            official = select_official_url(url, extract_title(html), candidates)
            if official and canonical_url(official).lower().rstrip("/") != canonical_url(url).lower().rstrip("/"):
                follow.append(official)
        title = extract_title(html)
        if follow:
            return DetailResult(
                title=title,
                fields=fields or blank_fields(),
                follow_links=tuple(follow),
                is_hop=True,
            )
        generic = is_generic_info_page(title, fields)
        if generic:
            return DetailResult(title=title, fields=blank_fields(), skip=True, skip_reason=generic)
        return DetailResult(
            title=title,
            fields=fields or blank_fields(),
        )
