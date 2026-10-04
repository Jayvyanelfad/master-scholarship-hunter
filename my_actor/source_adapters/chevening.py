"""Chevening discovery adapter.

Discovery covers the official scholarships page, the eligibility page, and
the course finder (all verified live on chevening.org). Verified facts:

- One-year UK Master's degrees for outstanding emerging leaders; the
  programme describes itself as fully funded.
- Eligibility requires citizenship of a Chevening-eligible country (Benin is
  listed in the country selector) plus at least two years' post-undergraduate
  work experience (2,800 hours). The fixed student profile contains no
  work-history data, so any Chevening record whose requirement text states
  the work-experience rule carries ``profile_requirements_missing =
  ["work_experience"]`` and can never be a guaranteed strong match.
- UK residents at application time are ineligible; an India-based applicant
  is unaffected by that clause.
- Applicants apply to three eligible UK Master's courses; the actual course
  pages carry field evidence. A Chevening record without a verified eligible
  course stays possible at best.
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

CHEVENING_DOMAINS = ("chevening.org", "www.chevening.org")
DISCOVERY_URLS = (
    "https://www.chevening.org/scholarships/",
    "https://www.chevening.org/resource-hub/guidance/eligibility/",
    "https://www.chevening.org/scholarships/find-a-course/",
)

ELIGIBILITY_PATH_HINTS = ("eligibility", "who-can-apply", "guidance")
COURSE_PATH_HINTS = ("course", "find-a-course", "university", "masters", "msc")


class CheveningAdapter(SourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            source_id="chevening",
            display_name="Chevening",
            source_type="official_government",
            discovery_urls=DISCOVERY_URLS,
            discovery_strategy="overview_then_eligibility_then_courses",
            pagination="bounded_listing_links",
            max_pages=8,
            max_records=40,
            official_domains=CHEVENING_DOMAINS,
            destination="United Kingdom",
            detail_is_official=True,
            enabled=True,
            status_reason="Official scholarships, eligibility, and course-finder pages verified live; work-experience rule captured as a profile gap.",
            notes="Never assume the user qualifies; work experience is required and unknown for this profile.",
        )

    def is_listing_url(self, url: str) -> bool:
        if not host_in_domains(url, CHEVENING_DOMAINS):
            return False
        return url.rstrip("/").lower() in {item.lower().rstrip("/") for item in DISCOVERY_URLS}

    def is_detail_url(self, url: str) -> bool:
        if not host_in_domains(url, CHEVENING_DOMAINS):
            return False
        if self.is_listing_url(url):
            return False
        lowered = url.lower()
        return any(hint in lowered for hint in ELIGIBILITY_PATH_HINTS + COURSE_PATH_HINTS + ("scholarship",))

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

    def extract_country_options(self, html: str) -> str:
        """Return the country-selector options as an eligible-country list."""
        options = re.findall(r"<option[^>]*>([^<>]{2,60})</option>", html or "", flags=re.I)
        cleaned = [re.sub(r"\s+", " ", option).strip() for option in options]
        cleaned = [option for option in cleaned if option.lower() not in {"select country", "select your award", "scholarship", "fellowship"}]
        return ", ".join(cleaned[:300])

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
                "fully-funded", "fully funded", "tuition", "stipend",
                "living", "allowance", "airfare", "travel",
            ))
        if not fields["nationality"]:
            fields["nationality"] = extract_evidence_sentences(text, (
                "chevening-eligible country", "eligible country", "citizen of",
                "all over the world", "international",
            ))
        countries = self.extract_country_options(html)
        if countries and not fields["nationality"]:
            fields["nationality"] = f"Chevening-eligible countries: {countries}"
        requirement_text = " ".join(
            sentence for sentence in re.split(r"(?<=[.!?])\s+", text)
            if "work experience" in sentence.lower() or "2,800 hours" in sentence or "2800 hours" in sentence
        )[:1200]
        return DetailResult(
            title=extract_title(html),
            fields=fields or blank_fields(),
            requirement_text=requirement_text,
        )
