"""Generic configured adapter for official single-destination sources.

Priority-2 sources (Finland, Norway, Sweden, Switzerland, Austria,
Australia, ...) are real official discovery entries that share one honest
parsing strategy instead of eleven near-identical files:

- start from verified official discovery URLs;
- follow only same-domain links whose path or anchor text looks like a
  scholarship/funding/programme page;
- parse detail pages with the shared structured-field extractor;
- never invent country lists, deadlines, or benefits.

A source stays ``enabled = False`` with a documented reason until its
discovery URL is verified live (see module docstrings per source).
"""

from __future__ import annotations

import re
import re
from dataclasses import dataclass

from .base import (
    fill_prose_evidence,
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
    is_generic_info_page,
    is_junk_page,
)
from ..verification import extract_structured_fields

LISTING_ANCHOR_HINTS = ("scholarship", "funding", "grant", "apply", "master", "programme", "award", "finance", "bursary")
DETAIL_PATH_HINTS = ("scholarship", "funding", "grant", "award", "programme", "program", "master", "finance", "excellence", "global-professional", "australia-award")

# A link target is only a scholarship-record candidate when its path names
# the award itself. Programme catalogues, university lists, and portals use
# generic words (study/master/program/finance) that must not qualify alone.
RECORD_PATH_TOKENS = (
    "scholarship", "scholarships", "fellowship", "fellowships", "grant",
    "grants", "award", "awards", "bursary", "bursaries", "stipend",
    "stipends", "excellence",
)
# Pagination links are discovery scaffolding, never records.
PAGINATION_PATTERNS = (
    re.compile(r"[?&](page|p|offset|start)=\d+", re.I),
    re.compile(r"/page/\d+", re.I),
)
# Utility/navigation paths that are never scholarship records.
NON_RECORD_PATH_TOKENS = (
    "cookie", "/faq", "accessibility", "/news", "/events", "/contact",
    "/sitemap", "/search", "newsletter", "alumni-stories", "/stories",
)

REQUIREMENT_SENTENCE_HINTS = ("work experience", "leadership", "2800 hours", "2,800 hours")


@dataclass
class AdapterConfig:
    source_id: str
    display_name: str
    source_type: str
    discovery_urls: tuple[str, ...]
    official_domains: tuple[str, ...]
    destination: str
    discovery_strategy: str
    enabled: bool
    status_reason: str
    max_records: int = 25
    max_pages: int = 3
    notes: str = ""
    # Extra path tokens that name genuine records for this source
    # (programme-track slugs etc.) beyond the shared award vocabulary.
    record_path_hints: tuple[str, ...] = ()


class ConfiguredOfficialAdapter(SourceAdapter):
    """A real adapter driven by a verified per-source config."""

    def __init__(self, config: AdapterConfig) -> None:
        super().__init__(
            source_id=config.source_id,
            display_name=config.display_name,
            source_type=config.source_type,
            discovery_urls=config.discovery_urls,
            discovery_strategy=config.discovery_strategy,
            pagination="bounded_listing_links",
            max_pages=config.max_pages,
            max_records=config.max_records,
            official_domains=config.official_domains,
            destination=config.destination,
            detail_is_official=True,
            enabled=config.enabled,
            status_reason=config.status_reason,
            notes=config.notes,
        )
        self._config_hints = tuple(config.record_path_hints)

    def _is_record_path(self, absolute: str) -> bool:
        lowered = absolute.lower()
        if any(token in lowered for token in RECORD_PATH_TOKENS):
            return True
        return any(hint in lowered for hint in self._config_hints)

    def _is_pagination(self, absolute: str) -> bool:
        return any(pattern.search(absolute) for pattern in PAGINATION_PATTERNS)

    def is_listing_url(self, url: str) -> bool:
        if url.rstrip("/").lower() in {item.rstrip("/").lower() for item in self.discovery_urls}:
            return True
        return super().is_listing_url(url)

    def is_detail_url(self, url: str) -> bool:
        if not host_in_domains(url, self.official_domains):
            return False
        if url.rstrip("/").lower() in {item.rstrip("/").lower() for item in self.discovery_urls}:
            return False
        if self._is_pagination(url):
            return False
        lowered = url.lower()
        if any(hint in lowered for hint in DETAIL_PATH_HINTS):
            return True
        return self._is_record_path(url)

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        from .base import canonical_programme_url, matches_nav_anchor

        found: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        next_page: str | None = None
        for href, anchor in extract_links(html):
            absolute = absolutize(base_url, href)
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            if not host_in_domains(absolute, self.official_domains):
                continue
            lowered = absolute.lower()
            if any(token in lowered for token in NON_RECORD_PATH_TOKENS):
                continue
            if self._is_pagination(absolute):
                if next_page is None:
                    next_page = absolute
                continue
            if matches_nav_anchor(anchor):
                continue
            anchor_lower = anchor.lower()
            if len(anchor_lower.strip()) < 6:
                continue
            if not (self._is_record_path(absolute) or any(hint in anchor_lower for hint in LISTING_ANCHOR_HINTS)):
                continue
            identity = canonical_programme_url(absolute)
            if identity in seen or identity in {item.lower().rstrip("/") for item in self.discovery_urls}:
                continue
            seen.add(identity)
            found.append(DiscoveryCandidate(url=absolute, title=anchor, context=anchor))
            if len(found) >= self.max_records:
                break
        return ListingResult(candidates=tuple(found), next_page_url=next_page)

    def parse_detail(self, html: str, url: str) -> DetailResult:
        junk = is_junk_page(html, url)
        if junk:
            return DetailResult(title=extract_title(html), fields=blank_fields(), skip=True, skip_reason=junk)
        text = extract_text(html)
        fields = extract_structured_fields(text)
        fields = fill_prose_evidence(fields, text, extract_title(html))
        if not fields["destination"] and self.destination:
            fields["destination"] = self.destination
        if not fields["funding"]:
            fields["funding"] = extract_evidence_sentences(text, (
                "tuition", "fee waiver", "stipend", "living", "allowance",
                "fully funded", "scholarship covers", "grant covers",
            ))
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, (
                "eligible countr", "open to", "international", "nationals",
                "citizens of", "all countries",
            ))
        title = extract_title(html)
        generic = is_generic_info_page(title, fields)
        if generic:
            return DetailResult(title=title, fields=blank_fields(), skip=True, skip_reason=generic)
        requirement_text = " ".join(
            sentence for sentence in re.split(r"(?<=[.!?])\s+", text)
            if any(hint in sentence.lower() for hint in REQUIREMENT_SENTENCE_HINTS)
        )[:1200]
        return DetailResult(
            title=title,
            fields=fields,
            requirement_text=requirement_text,
        )


PRIORITY_2_CONFIGS: tuple[AdapterConfig, ...] = (
    AdapterConfig(
        source_id="si_sweden",
        display_name="Swedish Institute",
        source_type="official_government",
        discovery_urls=("https://si.se/en/apply/scholarships/",),
        official_domains=("si.se",),
        destination="Sweden",
        discovery_strategy="listing_then_detail",
        enabled=True,
        status_reason="Discovery index verified live; Global Professionals and Pioneering Women in STEM tracks listed. Work-experience and leadership requirements are captured as profile gaps, never assumed.",
        notes="Do not assume Benin eligibility without checking the current country list on the track page.",
        record_path_hints=("global-professional", "pioneering", "sisgp"),
    ),
    AdapterConfig(
        source_id="finland",
        display_name="Study in Finland",
        source_type="official_government",
        discovery_urls=("https://www.studyinfinland.fi/scholarships",),
        official_domains=("studyinfinland.fi",),
        destination="Finland",
        discovery_strategy="listing_then_detail",
        enabled=True,
        status_reason="Discovery entry verified live; the official page itself warns university scholarships usually cover tuition only, so the strict matcher rejects partial awards.",
        notes="Focus only on fully funded Master's opportunities; tuition waivers must be rejected.",
    ),
    AdapterConfig(
        source_id="norway",
        display_name="Study in Norway",
        source_type="official_government",
        discovery_urls=("https://www.studyinnorway.no/",),
        official_domains=("studyinnorway.no",),
        destination="Norway",
        discovery_strategy="listing_then_detail",
        enabled=True,
        status_reason="Official portal verified live; it states Norway offers no individual scholarships open to all international students, so records are expected to reject on funding.",
        notes="Free/low tuition is not full funding. Only verified tuition plus living support qualifies.",
    ),
    AdapterConfig(
        source_id="switzerland",
        display_name="Swiss Government Excellence Scholarships (ESKAS)",
        source_type="official_government",
        discovery_urls=("https://www.sbfi.admin.ch/sbfi/en/home/education/scholarships-and-grants/swiss-government-excellence-scholarships.html",),
        official_domains=("sbfi.admin.ch", "admin.ch"),
        destination="Switzerland",
        discovery_strategy="listing_then_detail",
        enabled=True,
        status_reason="ESKAS page verified live; research scholarships require a completed Master's (doctoral track) and art scholarships are arts-only, so the strict matcher rejects non-CS/doctoral records.",
        notes="Never treat doctoral/postdoctoral tracks as Master's opportunities.",
    ),
    AdapterConfig(
        source_id="austria",
        display_name="OeAD grants.at",
        source_type="official_government",
        discovery_urls=("https://oead.at/en/to-austria/grants-and-scholarships/",),
        official_domains=("oead.at", "grants.at"),
        destination="Austria",
        discovery_strategy="listing_then_detail",
        enabled=True,
        status_reason="OeAD grants database entry verified live as the Austrian scholarship database.",
        notes="Verify Master's level and full funding per grant; database result pages are JS-driven.",
    ),
    AdapterConfig(
        source_id="australia",
        display_name="Australia Awards Africa",
        source_type="official_government",
        discovery_urls=("https://www.australiaawardsafrica.org/",),
        official_domains=("australiaawardsafrica.org", "australiaawards.org"),
        destination="Australia",
        discovery_strategy="listing_then_detail",
        enabled=True,
        status_reason="Australia Awards Africa portal verified live with a Masters scholarship track for Africans from eligible countries.",
        notes="Verify the current eligible-country list and call; do not assume Benin is included.",
        record_path_hints=("masters-scholarship", "award", "apply-for-an-award"),
    ),
    AdapterConfig(
        source_id="eiffel",
        display_name="Eiffel Excellence (Campus France)",
        source_type="official_government",
        discovery_urls=("https://www.campusfrance.org/en/",),
        official_domains=("campusfrance.org",),
        destination="France",
        discovery_strategy="listing_then_detail",
        enabled=False,
        status_reason="Disabled: no current Eiffel call URL could be verified (known Campus France Eiffel paths return 404 after the site migration). Enable with a verified current Eiffel call URL.",
        notes="Eiffel benefits must be checked against full funding; monthly allowance alone is not tuition coverage.",
    ),
    AdapterConfig(
        source_id="canada",
        display_name="EduCanada Scholarships",
        source_type="official_government",
        discovery_urls=("https://www.educanada.ca/scholarships-bourses/index.aspx?lang=eng",),
        official_domains=("educanada.ca",),
        destination="Canada",
        discovery_strategy="listing_then_detail",
        enabled=False,
        status_reason="Disabled: educanada.ca was unreachable from the verification environment (transport errors), so no discovery URL is verified. Vanier must never be used as it is doctoral-focused.",
        notes="Focus on Master's-level fully funded opportunities only.",
    ),
    AdapterConfig(
        source_id="denmark",
        display_name="Study in Denmark",
        source_type="official_government",
        discovery_urls=("https://studyindenmark.dk/",),
        official_domains=("studyindenmark.dk", "ufm.dk"),
        destination="Denmark",
        discovery_strategy="listing_then_detail",
        enabled=False,
        status_reason="Disabled: studyindenmark.dk was unreachable from the verification environment, so no discovery URL is verified.",
        notes="Only Master's scholarships with verified full funding qualify.",
    ),
    AdapterConfig(
        source_id="luxembourg",
        display_name="University of Luxembourg",
        source_type="official_university",
        discovery_urls=("https://www.uni.lu/",),
        official_domains=("uni.lu",),
        destination="Luxembourg",
        discovery_strategy="listing_then_detail",
        enabled=False,
        status_reason="Disabled: no University of Luxembourg scholarship discovery URL could be verified (uni.lu blocks non-browser fetches).",
        notes="Only Master's-level fully funded opportunities qualify.",
    ),
    AdapterConfig(
        source_id="singapore",
        display_name="Singapore Universities",
        source_type="official_university",
        discovery_urls=(),
        official_domains=("edu.sg",),
        destination="Singapore",
        discovery_strategy="listing_then_detail",
        enabled=False,
        status_reason="Disabled: no single official Singapore Master's scholarship discovery source is verified; opportunities are university-specific and no guessed URLs are used.",
        notes="Only Master's-level fully funded opportunities qualify.",
    ),
)


def build_configured_adapters() -> list[ConfiguredOfficialAdapter]:
    return [ConfiguredOfficialAdapter(config) for config in PRIORITY_2_CONFIGS]
