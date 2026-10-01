"""Scholarship crawler and profile matcher."""

from __future__ import annotations

import re

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawlingContext
from crawlee.router import Router

router = Router[BeautifulSoupCrawlingContext]()


# =========================
# YOUR PROFILE
# =========================

STUDENT_PROFILE = {
    "nationality": "Benin Republic",
    "date_of_birth": "2002-03-13",
    "cgpa": 6.0,
    "study_level": "Master's",
}


# =========================
# HELPER FUNCTIONS
# =========================

def clean_text(text: str) -> str:
    """Clean whitespace from scraped text."""
    return re.sub(r"\s+", " ", text).strip()


def find_cgpa_requirements(text: str) -> list[str]:
    """Find sentences containing CGPA/GPA requirements."""
    sentences = re.split(r"(?<=[.!?])\s+", text)

    matches = []

    for sentence in sentences:
        lower = sentence.lower()

        if any(word in lower for word in [
            "cgpa",
            "gpa",
            "grade point",
            "minimum grade",
            "academic requirement",
        ]):
            matches.append(sentence[:500])

    return matches[:10]


def find_nationality_requirements(text: str) -> list[str]:
    """Find nationality/citizenship eligibility information."""
    sentences = re.split(r"(?<=[.!?])\s+", text)

    matches = []

    for sentence in sentences:
        lower = sentence.lower()

        if any(word in lower for word in [
            "nationality",
            "citizen",
            "citizenship",
            "international student",
            "international students",
            "developing countries",
            "eligible countries",
        ]):
            matches.append(sentence[:500])

    return matches[:10]


def calculate_match(text: str) -> dict:
    """Estimate whether the scholarship may match the student profile."""

    lower = text.lower()

    score = 0
    reasons = []
    warnings = []

    # ---------------------------------
    # Master's study
    # ---------------------------------

    if any(term in lower for term in [
        "master's",
        "master’s",
        "masters",
        "msc",
        "graduate",
        "postgraduate",
    ]):
        score += 30
        reasons.append("Master's/graduate study appears to be supported.")
    else:
        warnings.append(
            "Master's eligibility was not clearly detected."
        )

    # ---------------------------------
    # International eligibility
    # ---------------------------------

    if any(term in lower for term in [
        "international students",
        "international student",
        "international applicants",
        "international applicant",
        "all nationalities",
        "any nationality",
        "foreign students",
    ]):
        score += 30
        reasons.append(
            "The page appears to mention international applicants."
        )

    # Benin / Africa / developing-country indicators
    if any(term in lower for term in [
        "benin",
        "africa",
        "african countries",
        "developing countries",
        "least developed countries",
    ]):
        score += 20
        reasons.append(
            "Benin/Africa/developing-country eligibility may be relevant."
        )

    # ---------------------------------
    # Academic requirements
    # ---------------------------------

    cgpa_requirements = find_cgpa_requirements(text)

    if cgpa_requirements:
        score += 10
        reasons.append(
            "Academic/GPA/CGPA requirements were found and should be reviewed."
        )
        warnings.append(
            "CGPA scale varies between institutions; do not assume "
            "6.0 is directly comparable until the scholarship's scale is confirmed."
        )
    else:
        warnings.append(
            "No explicit CGPA/GPA requirement was detected."
        )

    # ---------------------------------
    # Exclusion indicators
    # ---------------------------------

    if any(term in lower for term in [
        "indian citizens only",
        "indian nationals only",
        "only indian",
        "for indian students only",
    ]):
        score -= 60
        warnings.append(
            "The page appears to restrict eligibility to Indian applicants."
        )

    # ---------------------------------
    # Result classification
    # ---------------------------------

    if score >= 60:
        match_status = "POTENTIAL_MATCH"
    elif score >= 30:
        match_status = "REVIEW"
    else:
        match_status = "LOW_MATCH"

    return {
        "match_status": match_status,
        "match_score": max(0, min(score, 100)),
        "reasons": reasons,
        "warnings": warnings,
        "cgpa_requirements": cgpa_requirements,
        "nationality_requirements": find_nationality_requirements(text),
    }


# =========================
# CRAWLER
# =========================

@router.default_handler
async def default_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:
    """Scrape scholarship pages and compare them with the student profile."""

    url = context.request.url

    Actor.log.info(f"Scraping {url}...")

    # Get complete visible page text.
    page_text = clean_text(
        context.soup.get_text(" ", strip=True)
    )

    title = (
        clean_text(context.soup.title.get_text())
        if context.soup.title
        else None
    )

    h1s = [
        clean_text(h.get_text(" ", strip=True))
        for h in context.soup.find_all("h1")
    ]

    h2s = [
        clean_text(h.get_text(" ", strip=True))
        for h in context.soup.find_all("h2")
    ]

    h3s = [
        clean_text(h.get_text(" ", strip=True))
        for h in context.soup.find_all("h3")
    ]

    # Calculate potential match.
    match = calculate_match(page_text)

    # Store result.
    data = {
        "url": url,
        "title": title,

        "student_profile": STUDENT_PROFILE,

        "match_status": match["match_status"],
        "match_score": match["match_score"],

        "reasons": match["reasons"],
        "warnings": match["warnings"],

        "cgpa_requirements": match["cgpa_requirements"],
        "nationality_requirements": match["nationality_requirements"],

        "h1s": h1s,
        "h2s": h2s,
        "h3s": h3s,
    }

    await context.push_data(data)

    # Continue following links.
    await context.enqueue_links()
