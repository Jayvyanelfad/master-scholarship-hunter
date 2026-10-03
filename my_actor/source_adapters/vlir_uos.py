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
from ..verification import extract_structured_fields

VLIR_DOMAINS = ("vliruos.be", "www.vliruos.be")
DISCOVERY_URLS = (
    "https://www.vliruos.be/get-funded/study-scholarships",
    "https://www.vliruos.be/",
)

PROGRAMME_HINTS = ("master", "bachelor", "programme", "program", "study", "scholarship", "icp")
COUNTRY_LIST_HINTS = ("eligible countr", "participating countr", "country list", "scholarship countr")
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
        return any(hint in lowered for hint in PROGRAMME_HINTS) and lowered.rstrip("/") not in {
            item.lower().rstrip("/") for item in DISCOVERY_URLS
        }

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
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
        text = extract_text(html)
        fields = extract_structured_fields(text)
        if not fields["destination"]:
            fields["destination"] = self.destination
        residence = self.extract_residence_list(text)
        # A residence-rule sentence without an extractable country list keeps
        # residence unknown (never eligible): the matcher must see the list.
        requirement_text = " ".join(
            sentence for sentence in re.split(r"(?<=[.!?])\s+", text)
            if "work experience" in sentence.lower() or "leadership" in sentence.lower()
        )[:1200]
        notes = []
        if re.search(r"call .* (is now )?closed|applications are closed", text, re.I):
            notes.append("Official call status indicates a closed cycle; deadlines must be current to qualify.")
        return DetailResult(
            title=extract_title(html),
            fields=fields or blank_fields(),
            residence_countries=residence,
            requirement_text=requirement_text,
            notes=tuple(notes),
        )
