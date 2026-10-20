"""VLIR-UOS ICP Connect discovery adapter.

Discovery starts at the official study-scholarships page (verified live),
which lists ICP Connect initial and advanced Master's programmes. Verified
facts encoded from the official pages:

- Scholarships go to applicants from 29 eligible countries in Africa, Asia,
  and Latin America for English-taught programmes at Flemish institutions.
- Candidates must hold an eligible nationality AND reside in an eligible
  country at application. Residence in India therefore fails even when
  Beninese nationality passes; the adapter keeps the residence list in
  ``residence_countries`` so the matcher can decide.
- ICP Connect covers tuition fees, travel, insurance, and living expenses
  (board and lodging) for the full programme duration; partial scholarships
  do not exist in this framework.
- Calls can be between cycles (the 2026-2027 call was closed with the next
  expected mid-November 2026). A closed call without a future deadline must
  never be treated as active.

Benin is never hardcoded: eligibility always comes from the specific
programme/call page.
"""

from __future__ import annotations

import re

from .base import (
    fill_prose_evidence,
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

VLIR_DOMAINS = ("vliruos.be", "www.vliruos.be")
DISCOVERY_URLS = (
    "https://www.vliruos.be/get-funded/study-scholarships",
    "https://www.vliruos.be/",
)

# Only ICP Connect Master's programme pages are candidates.
MASTER_PATH_HINTS = ("master", "icp-connect", "icp_connect", "study-programme", "study-programmes")
# Never candidates: bachelor's, jobs, project funding, short initiatives.
EXCLUDED_PATH_HINTS = (
    "bachelor", "hotel-management", "jobs", "job-", "vacancy", "vacancies",
    "career", "project-funding", "short-initiative", "staff", "alumni-network",
    "programme-manager", "programme manager",
)
EXCLUDED_ANCHOR_HINTS = (
    "bachelor", "programme manager", "project funding", "short initiative",
    "call for project", "job", "vacancy",
)

FUNDING_PROSE_KEYWORDS = (
    "tuition fees", "tuition", "living expenses", "board and lodging",
    "stipend", "allowance", "travel", "insurance", "costs are covered",
    "scholarship costs",
)
NATIONALITY_PROSE_KEYWORDS = (
    "eligible countries", "nationality", "applicants from", "candidates",
    "scholarship countries", "africa", "asia", "latin america",
)
ELIGIBLE_LIST_LABELS = ("Eligible countries", "Eligible country", "Eligible nationalities", "Scholarship countries")


class VlirUosAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="vlir_uos",
            display_name="VLIR-UOS",
            source_type="official_program",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="framework_then_programme_then_institution",
            pagination="bounded_listing_links",
            max_pages=8,
            max_records=40,
            official_domains=VLIR_DOMAINS,
            destination="Belgium",
            detail_is_official=True,
            enabled=True,
            status_reason="Official ICP Connect framework verified live, including the 29-country rule, residence requirement, and full cost coverage.",
            notes="Extract eligibility from the specific current programme/call; never hardcode Benin.",
        )

    def is_listing_url(self, url: str) -> bool:
        if not host_in_domains(url, VLIR_DOMAINS):
            return False
        lowered = url.lower().rstrip("/")
        if any(item.lower().rstrip("/") == lowered for item in DISCOVERY_URLS):
            return True
        return "scholarship" in lowered and not self.is_detail_url(url)

    def is_detail_url(self, url: str) -> bool:
        if not host_in_domains(url, VLIR_DOMAINS):
            return False
        lowered = url.lower()
        if lowered.rstrip("/") in {item.lower().rstrip("/") for item in DISCOVERY_URLS}:
            return False
        if any(hint in lowered for hint in EXCLUDED_PATH_HINTS):
            return False
        return any(hint in lowered for hint in MASTER_PATH_HINTS)

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
            if any(hint in anchor.lower() for hint in EXCLUDED_ANCHOR_HINTS):
                continue
            identity = canonical_programme_url(absolute)
            if identity in seen:
                continue
            seen.add(identity)
            found.append(DiscoveryCandidate(url=absolute, title=anchor, context=anchor))
            if len(found) >= self.max_records:
                break
        return ListingResult(candidates=tuple(found))

    def extract_residence_list(self, text: str) -> str:
        """Return an eligible-country residence list, or "" when absent.

        Only explicit eligible-country lists qualify; free prose about
        studying abroad is never treated as a residence rule.
        """
        for label in ELIGIBLE_LIST_LABELS:
            match = re.search(rf"\b{re.escape(label)}\b\s*[:\-]?\s*(.{{1,400}}?)(?=\s+[A-Z][a-z]+:|\s*$)", text)
            if match and ("," in match.group(1) or " and " in match.group(1)):
                return re.sub(r"\s+", " ", match.group(1)).strip()
        return ""

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
            fields["funding"] = extract_evidence_sentences(text, FUNDING_PROSE_KEYWORDS)
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, NATIONALITY_PROSE_KEYWORDS)
        residence = self.extract_residence_list(text)
        # A residence-rule sentence without an extractable country list keeps
        # residence unknown (never eligible): the matcher must see the list.
        requirement_text = " ".join(
            sentence for sentence in re.split(r"(?<=[.!?])\s+", text)
            if "work experience" in sentence.lower() or "leadership" in sentence.lower()
        )[:1200]
        title = extract_title(html)
        generic = is_generic_info_page(title, fields)
        if generic:
            return DetailResult(title=title, fields=blank_fields(), skip=True, skip_reason=generic)
        notes = []
        if re.search(r"call .* (is now )?closed|applications are closed", text, re.I):
            notes.append("Official call status indicates a closed cycle; deadlines must be current to qualify.")
        return DetailResult(
            title=title,
            fields=fields or blank_fields(),
            residence_countries=residence,
            requirement_text=requirement_text,
            notes=tuple(notes),
        )
