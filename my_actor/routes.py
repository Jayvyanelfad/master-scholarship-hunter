"""
Scholarship Hunter router.

Scrapes scholarship pages and evaluates them against the student's profile.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawlingContext
from crawlee.router import Router


router = Router[BeautifulSoupCrawlingContext]()


# ============================================================
# STUDENT PROFILE
# ============================================================

STUDENT_PROFILE = {
    "full_name": "Student",
    "nationality": "Benin",
    "country_of_citizenship": "Benin",
    "date_of_birth": "2002-03-13",
    "cgpa": 6.0,
    "cgpa_scale": 10.0,

    # Target study
    "degree": "Master's",
    "field_of_study": "Computer Science",
    "study_level": "Masters",

    # Preferred destinations
    "preferred_destinations": [
        "Germany",
        "France",
        "Netherlands",
        "Belgium",
        "Finland",
        "Sweden",
        "Norway",
        "Denmark",
        "Canada",
        "Australia",
        "United Kingdom",
        "USA",
        "Malaysia",
    ],

    # Important preference
    "exclude_india_only_scholarships": True,
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_text(value: str | None) -> str:
    """Normalize whitespace."""
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def calculate_age(dob: str) -> int:
    """Calculate current age from YYYY-MM-DD."""
    birth_date = datetime.strptime(dob, "%Y-%m-%d").date()
    today = date.today()

    age = today.year - birth_date.year

    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    return age


def normalize_url(url: str) -> str:
    """Remove tracking parameters from URLs where possible."""
    return url.split("?")[0].rstrip("/")


def contains_any(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword occurs in text."""
    text_lower = text.lower()

    return any(keyword.lower() in text_lower for keyword in keywords)


def extract_deadline(text: str) -> str | None:
    """Try to find a scholarship deadline in page text."""

    patterns = [
        r"deadline\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"deadline\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"deadline\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"application\s+deadline\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return clean_text(match.group(1))

    return None


def detect_nationality_requirement(text: str) -> dict[str, Any]:
    """
    Determine whether the scholarship appears to restrict nationality.

    This intentionally uses conservative rules. Unknown means we do not
    assume the scholarship is eligible or ineligible.
    """

    text_lower = text.lower()

    # Clearly India-specific
    india_only_patterns = [
        "indian students only",
        "only indian students",
        "indian nationals only",
        "citizens of india only",
        "indian citizen",
        "indian citizens",
        "for indian students",
        "scholarship for indian students",
    ]

    if contains_any(text_lower, india_only_patterns):
        return {
            "status": "likely_not_eligible",
            "requirement": "India-specific",
            "evidence": "Page contains an India-specific nationality requirement.",
        }

    # Clearly international
    international_patterns = [
        "international students",
        "international student",
        "students from all countries",
        "all nationalities",
        "any nationality",
        "international applicants",
        "foreign students",
        "non-eu students",
        "non-eu nationals",
    ]

    if contains_any(text_lower, international_patterns):
        return {
            "status": "likely_eligible",
            "requirement": "International applicants accepted",
            "evidence": "Page indicates eligibility for international applicants.",
        }

    return {
        "status": "unknown",
        "requirement": None,
        "evidence": None,
    }


def detect_degree_requirement(text: str) -> dict[str, Any]:
    """Check whether the page appears relevant to Master's study."""

    text_lower = text.lower()

    masters_keywords = [
        "master's",
        "master’s",
        "masters",
        "master degree",
        "graduate degree",
        "msc",
        "m.sc",
        "ma ",
        "m.a.",
        "graduate studies",
    ]

    phd_keywords = [
        "phd",
        "doctoral",
        "doctorate",
    ]

    if contains_any(text_lower, masters_keywords):
        return {
            "status": "likely_eligible",
            "requirement": "Master's/graduate study",
        }

    if contains_any(text_lower, phd_keywords):
        return {
            "status": "likely_not_eligible",
            "requirement": "PhD/doctoral study",
        }

    return {
        "status": "unknown",
        "requirement": None,
    }


def detect_field_requirement(text: str) -> dict[str, Any]:
    """Check whether Computer Science/IT appears relevant."""

    text_lower = text.lower()

    field_keywords = [
        "computer science",
        "computer sciences",
        "information technology",
        "information systems",
        "software engineering",
        "data science",
        "artificial intelligence",
        "machine learning",
        "cybersecurity",
        "cyber security",
        "computing",
    ]

    if contains_any(text_lower, field_keywords):
        return {
            "status": "likely_eligible",
            "requirement": "Computer Science / IT / related field",
        }

    return {
        "status": "unknown",
        "requirement": None,
    }


def detect_destination(
    text: str,
    url: str,
) -> dict[str, Any]:
    """Find the destination country mentioned by the scholarship."""

    combined = f"{text} {url}".lower()

    countries = [
        "Germany",
        "France",
        "Netherlands",
        "Belgium",
        "Finland",
        "Sweden",
        "Norway",
        "Denmark",
        "Canada",
        "Australia",
        "United Kingdom",
        "UK",
        "USA",
        "United States",
        "Malaysia",
        "Ireland",
        "Switzerland",
        "Austria",
        "New Zealand",
        "Japan",
        "South Korea",
    ]

    found = []

    for country in countries:
        if country.lower() in combined:
            found.append(country)

    preferred = [
        country
        for country in found
        if country in STUDENT_PROFILE["preferred_destinations"]
        or (
            country == "UK"
            and "United Kingdom"
            in STUDENT_PROFILE["preferred_destinations"]
        )
        or (
            country == "USA"
            and "USA"
            in STUDENT_PROFILE["preferred_destinations"]
        )
    ]

    return {
        "countries_detected": list(dict.fromkeys(found)),
        "preferred_destination_match": list(dict.fromkeys(preferred)),
    }


def extract_cgpa_requirement(text: str) -> str | None:
    """Extract simple CGPA/GPA requirements."""

    patterns = [
        r"(?:minimum\s+)?CGPA\s*(?:of|:|>=|>)?\s*(\d+(?:\.\d+)?)",
        r"(?:minimum\s+)?GPA\s*(?:of|:|>=|>)?\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*/\s*10\s*(?:CGPA|GPA)?",
        r"(\d+(?:\.\d+)?)\s*/\s*4\s*(?:CGPA|GPA)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return match.group(0)

    return None


def evaluate_cgpa(text: str) -> dict[str, Any]:
    """Compare student's CGPA with an explicitly detected requirement."""

    requirement = extract_cgpa_requirement(text)

    if not requirement:
        return {
            "status": "unknown",
            "student_cgpa": STUDENT_PROFILE["cgpa"],
            "requirement": None,
        }

    match = re.search(
        r"(\d+(?:\.\d+)?)",
        requirement,
    )

    if not match:
        return {
            "status": "unknown",
            "student_cgpa": STUDENT_PROFILE["cgpa"],
            "requirement": requirement,
        }

    required = float(match.group(1))

    # Only compare directly when the requirement appears to use /10.
    if "/10" in requirement.lower():
        if STUDENT_PROFILE["cgpa"] >= required:
            status = "likely_eligible"
        else:
            status = "likely_not_eligible"
    else:
        status = "unknown"

    return {
        "status": status,
        "student_cgpa": STUDENT_PROFILE["cgpa"],
        "requirement": requirement,
    }


def calculate_match(
    *,
    nationality: dict[str, Any],
    degree: dict[str, Any],
    field: dict[str, Any],
    destination: dict[str, Any],
    cgpa: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate a transparent match score.

    This is a screening score, not an admission decision.
    """

    score = 0
    reasons: list[str] = []
    warnings: list[str] = []

    # --------------------------------------------------------
    # Nationality
    # --------------------------------------------------------

    if nationality["status"] == "likely_not_eligible":
        score -= 60
        warnings.append(
            "The scholarship appears to be restricted by nationality."
        )

    elif nationality["status"] == "likely_eligible":
        score += 25
        reasons.append(
            "The scholarship appears open to international applicants."
        )

    else:
        warnings.append(
            "Nationality eligibility could not be determined from the page."
        )

    # --------------------------------------------------------
    # Degree
    # --------------------------------------------------------

    if degree["status"] == "likely_eligible":
        score += 25
        reasons.append(
            "The scholarship appears relevant to Master's/graduate study."
        )

    elif degree["status"] == "likely_not_eligible":
        score -= 30
        warnings.append(
            "The scholarship appears targeted at PhD/doctoral study."
        )

    else:
        warnings.append(
            "Master's eligibility could not be confirmed."
        )

    # --------------------------------------------------------
    # Field
    # --------------------------------------------------------

    if field["status"] == "likely_eligible":
        score += 20
        reasons.append(
            "Computer Science/IT or a related field appears on the page."
        )

    else:
        warnings.append(
            "Computer Science/IT relevance could not be confirmed."
        )

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    if destination["preferred_destination_match"]:
        score += 20
        reasons.append(
            "The destination appears in the student's preferred countries."
        )
    else:
        warnings.append(
            "A preferred destination could not be confirmed."
        )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    if cgpa["status"] == "likely_eligible":
        score += 10
        reasons.append(
            "The student's CGPA appears to meet the detected requirement."
        )

    elif cgpa["status"] == "likely_not_eligible":
        score -= 20
        warnings.append(
            "The student's CGPA appears below the detected requirement."
        )

    else:
        warnings.append(
            "No directly comparable CGPA requirement was detected."
        )

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    score = max(0, min(100, score))

    if score >= 70:
        match_status = "strong_match"
    elif score >= 45:
        match_status = "possible_match"
    elif score >= 20:
        match_status = "low_match"
    else:
        match_status = "likely_not_match"

    # Hard nationality exclusion
    if (
        STUDENT_PROFILE["exclude_india_only_scholarships"]
        and nationality["status"] == "likely_not_eligible"
    ):
        match_status = "likely_not_eligible"

    return {
        "match_status": match_status,
        "match_score": score,
        "reasons": reasons,
        "warnings": warnings,
    }


# ============================================================
# REQUEST HANDLER
# ============================================================

@router.default_handler
async def default_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:
    """Scrape and evaluate each page."""

    url = context.request.url

    Actor.log.info(f"Scraping: {url}")

    soup = context.soup

    # --------------------------------------------------------
    # Basic page information
    # --------------------------------------------------------

    title = clean_text(
        soup.title.get_text(" ", strip=True)
        if soup.title
        else ""
    )

    h1s = [
        clean_text(element.get_text(" ", strip=True))
        for element in soup.find_all("h1")
    ]

    h2s = [
        clean_text(element.get_text(" ", strip=True))
        for element in soup.find_all("h2")
    ]

    h3s = [
        clean_text(element.get_text(" ", strip=True))
        for element in soup.find_all("h3")
    ]

    # Full visible page text
    page_text = clean_text(
        soup.get_text(" ", strip=True)
    )

    # --------------------------------------------------------
    # Scholarship evaluation
    # --------------------------------------------------------

    nationality = detect_nationality_requirement(
        page_text
    )

    degree = detect_degree_requirement(
        page_text
    )

    field = detect_field_requirement(
        page_text
    )

    destination = detect_destination(
        page_text,
        url,
    )

    cgpa = evaluate_cgpa(
        page_text
    )

    deadline = extract_deadline(
        page_text
    )

    match = calculate_match(
        nationality=nationality,
        degree=degree,
        field=field,
        destination=destination,
        cgpa=cgpa,
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    data = {
        # Page
        "title": title,
        "url": url,
        "h1s": h1s,
        "h2s": h2s,
        "h3s": h3s,

        # Student profile
        "student_profile": {
            "nationality": STUDENT_PROFILE["nationality"],
            "country_of_citizenship": STUDENT_PROFILE[
                "country_of_citizenship"
            ],
            "date_of_birth": STUDENT_PROFILE[
                "date_of_birth"
            ],
            "age": calculate_age(
                STUDENT_PROFILE["date_of_birth"]
            ),
            "cgpa": STUDENT_PROFILE["cgpa"],
            "cgpa_scale": STUDENT_PROFILE["cgpa_scale"],
            "degree": STUDENT_PROFILE["degree"],
            "field_of_study": STUDENT_PROFILE[
                "field_of_study"
            ],
            "preferred_destinations": STUDENT_PROFILE[
                "preferred_destinations"
            ],
        },

        # Matching
        "match_status": match["match_status"],
        "match_score": match["match_score"],
        "reasons": match["reasons"],
        "warnings": match["warnings"],

        # Requirements found on page
        "cgpa_requirements": cgpa,
        "nationality_requirements": nationality,
        "degree_requirements": degree,
        "field_requirements": field,

        # Destination
        "destination": destination,

        # Deadline
        "deadline": deadline,

        # Useful metadata
        "source_domain": "wemakescholars.com",
    }

    await context.push_data(data)

    # --------------------------------------------------------
    # Continue crawling links
    # --------------------------------------------------------

    await context.enqueue_links()

