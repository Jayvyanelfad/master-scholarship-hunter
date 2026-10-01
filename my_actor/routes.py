"""Scholarship crawler and matching logic."""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urlparse

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawlingContext
from crawlee.router import Router

router = Router[BeautifulSoupCrawlingContext]()


# ============================================================
# YOUR PROFILE
# ============================================================

STUDENT_PROFILE = {
    "nationality": "Benin",
    "country": "Benin",
    "date_of_birth": "2002-03-13",
    "cgpa": 6.0,
    "cgpa_scale": 10.0,
    "degree_level": "Master's",
    "field": "Computer Science",
    "field_keywords": [
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
        "informatics",
        "computing",
        "computer engineering",
        "technology",
        "IT",
    ],
    "preferred_destinations": [
        "Germany",
        "France",
        "Netherlands",
        "Belgium",
        "Finland",
        "Sweden",
        "Norway",
        "Denmark",
        "Austria",
        "Switzerland",
        "United Kingdom",
        "UK",
        "Ireland",
        "Canada",
        "Australia",
    ],
}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    """Normalize whitespace."""
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_title(context: BeautifulSoupCrawlingContext) -> str:
    """Get the page title safely."""
    if not context.soup.title:
        return ""

    return clean_text(context.soup.title.get_text(" ", strip=True))


def get_headings(context: BeautifulSoupCrawlingContext) -> tuple[list[str], list[str], list[str]]:
    """Extract H1/H2/H3 headings."""
    h1s = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in context.soup.find_all("h1")
    ]

    h2s = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in context.soup.find_all("h2")
    ]

    h3s = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in context.soup.find_all("h3")
    ]

    return h1s, h2s, h3s


def page_text(context: BeautifulSoupCrawlingContext) -> str:
    """Get useful visible text from the page."""
    soup = context.soup

    # Remove elements that create lots of irrelevant text.
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    return clean_text(text)


def contains_any(text: str, phrases: list[str]) -> bool:
    """Return True if any phrase occurs in text."""
    text_lower = text.lower()

    return any(
        phrase.lower() in text_lower
        for phrase in phrases
    )


# ============================================================
# SCHOLARSHIP DETECTION
# ============================================================

SCHOLARSHIP_SIGNALS = [
    "scholarship",
    "fellowship",
    "grant",
    "funding",
    "financial aid",
    "tuition waiver",
    "studentship",
    "award",
]

MASTER_SIGNALS = [
    "master's",
    "master’s",
    "masters",
    "msc",
    "m.sc",
    "graduate",
    "postgraduate",
    "graduate scholarship",
]

PHD_SIGNALS = [
    "phd",
    "ph.d",
    "doctoral",
    "doctorate",
]

BACHELOR_SIGNALS = [
    "bachelor",
    "bachelors",
    "undergraduate",
    "b.sc",
    "bsc",
]

EXCLUDED_LEVEL_SIGNALS = [
    "mba",
    "medicine",
    "mbbs",
    "md scholarship",
    "medical school",
    "dentistry",
    "pharmacy",
]


# ============================================================
# NATIONALITY ANALYSIS
# ============================================================

RESTRICTED_NATIONALITY_PATTERNS = [
    r"\bindian students only\b",
    r"\bindian nationals only\b",
    r"\bonly indian students\b",
    r"\bonly for indian students\b",
    r"\bfor indian citizens only\b",
    r"\bindian citizens only\b",
    r"\bindian nationals\b",
    r"\bcitizens of india\b",
    r"\bresidents of india only\b",
    r"\bpermanent residents of india\b",
]

INTERNATIONAL_PATTERNS = [
    r"\binternational students\b",
    r"\binternational applicants\b",
    r"\binternational candidates\b",
    r"\bstudents from all countries\b",
    r"\ball nationalities\b",
    r"\bany nationality\b",
    r"\bworldwide applicants\b",
    r"\bglobal applicants\b",
    r"\bforeign students\b",
]


def find_restricted_nationalities(text: str) -> list[str]:
    """Detect explicit nationality restrictions."""
    found = []

    for pattern in RESTRICTED_NATIONALITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if "India" not in found:
                found.append("India")

    return found


def detect_international_eligibility(text: str) -> bool:
    """Detect explicit international eligibility."""
    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in INTERNATIONAL_PATTERNS
    )


# ============================================================
# DEGREE ANALYSIS
# ============================================================

def detect_degree_requirements(
    title: str,
    text: str,
) -> dict:
    """Determine the likely degree level."""
    combined = f"{title} {text}".lower()

    is_master = contains_any(combined, MASTER_SIGNALS)
    is_phd = contains_any(combined, PHD_SIGNALS)
    is_bachelor = contains_any(combined, BACHELOR_SIGNALS)
    is_excluded = contains_any(combined, EXCLUDED_LEVEL_SIGNALS)

    # Strong title-level signal.
    title_lower = title.lower()

    title_master = contains_any(title_lower, MASTER_SIGNALS)
    title_phd = contains_any(title_lower, PHD_SIGNALS)
    title_bachelor = contains_any(title_lower, BACHELOR_SIGNALS)

    if title_master:
        level = "Master's"
    elif title_phd:
        level = "PhD"
    elif title_bachelor:
        level = "Bachelor's"
    elif is_phd and not is_master:
        level = "PhD"
    elif is_bachelor and not is_master:
        level = "Bachelor's"
    elif is_excluded:
        level = "Other"
    else:
        level = "Unknown"

    return {
        "level": level,
        "master_detected": is_master,
        "phd_detected": is_phd,
        "bachelor_detected": is_bachelor,
        "excluded_detected": is_excluded,
    }


# ============================================================
# FIELD ANALYSIS
# ============================================================

def detect_field_requirements(
    title: str,
    headings: list[str],
    text: str,
) -> dict:
    """Determine whether the page relates to CS/IT."""
    # Give title and headings more importance than arbitrary page text.
    title_and_headings = " ".join(
        [title] + headings
    ).lower()

    full_text = text.lower()

    matched_keywords = []

    for keyword in STUDENT_PROFILE["field_keywords"]:
        keyword_lower = keyword.lower()

        if keyword_lower in title_and_headings:
            matched_keywords.append(keyword)

    # Only search the full page for field signals when there wasn't
    # already a strong title/heading signal.
    if not matched_keywords:
        for keyword in STUDENT_PROFILE["field_keywords"]:
            keyword_lower = keyword.lower()

            if keyword_lower in full_text:
                matched_keywords.append(keyword)

    # Remove duplicates while preserving order.
    matched_keywords = list(dict.fromkeys(matched_keywords))

    return {
        "matches_student_field": bool(matched_keywords),
        "matched_keywords": matched_keywords,
    }


# ============================================================
# DESTINATION ANALYSIS
# ============================================================

DESTINATIONS = [
    "Germany",
    "France",
    "Netherlands",
    "Belgium",
    "Finland",
    "Sweden",
    "Norway",
    "Denmark",
    "Austria",
    "Switzerland",
    "United Kingdom",
    "UK",
    "Ireland",
    "Canada",
    "Australia",
    "United States",
    "USA",
    "United States of America",
    "Italy",
    "Spain",
    "Portugal",
    "Poland",
    "Czech Republic",
    "Japan",
    "South Korea",
    "Malaysia",
    "Singapore",
    "New Zealand",
]


def detect_destinations(
    title: str,
    url: str,
    text: str,
) -> list[str]:
    """Find likely scholarship destinations."""
    # Destination is much more reliable from title and URL.
    strong_text = f"{title} {url}".lower()

    destinations = []

    for country in DESTINATIONS:
        if country.lower() in strong_text:
            destinations.append(country)

    # If title/URL gave us nothing, use a smaller text search.
    if not destinations:
        text_lower = text.lower()

        for country in DESTINATIONS:
            if country.lower() in text_lower:
                destinations.append(country)

    return list(dict.fromkeys(destinations))


# ============================================================
# CGPA ANALYSIS
# ============================================================

def extract_cgpa_requirements(text: str) -> list[dict]:
    """Extract common CGPA/GPA requirements."""
    requirements = []

    patterns = [
        # CGPA 3.0/4.0
        r"(?:cgpa|gpa)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",

        # CGPA of 3.0 out of 4.0
        r"(?:cgpa|gpa)[^0-9]{0,40}"
        r"(\d+(?:\.\d+)?)\s+out\s+of\s+"
        r"(\d+(?:\.\d+)?)",

        # minimum CGPA 3.0
        r"(?:minimum|required|at least)[^0-9]{0,30}"
        r"(?:cgpa|gpa)[^0-9]{0,20}"
        r"(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                minimum = float(match.group(1))
            except (ValueError, TypeError):
                continue

            scale = None

            if match.lastindex and match.lastindex >= 2:
                try:
                    scale = float(match.group(2))
                except (ValueError, TypeError):
                    scale = None

            requirements.append(
                {
                    "minimum": minimum,
                    "scale": scale,
                    "raw": match.group(0),
                }
            )

    # Deduplicate.
    unique = []

    seen = set()

    for item in requirements:
        key = (
            item["minimum"],
            item["scale"],
        )

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def cgpa_assessment(requirements: list[dict]) -> dict:
    """Compare student's CGPA against detected requirements."""
    student_cgpa = float(STUDENT_PROFILE["cgpa"])
    student_scale = float(STUDENT_PROFILE["cgpa_scale"])

    if not requirements:
        return {
            "status": "unknown",
            "student_cgpa": student_cgpa,
            "student_scale": student_scale,
            "requirements": [],
        }

    assessments = []

    for requirement in requirements:
        minimum = requirement["minimum"]
        scale = requirement["scale"]

        if scale:
            # Normalize both values to a 10-point scale.
            normalized_requirement = (
                minimum / scale
            ) * student_scale

            meets = student_cgpa >= normalized_requirement

            assessments.append(
                {
                    "minimum": minimum,
                    "scale": scale,
                    "normalized_to_student_scale": round(
                        normalized_requirement,
                        2,
                    ),
                    "meets": meets,
                }
            )
        else:
            # If no scale is stated, do not pretend that the
            # number can safely be compared across grading systems.
            assessments.append(
                {
                    "minimum": minimum,
                    "scale": None,
                    "normalized_to_student_scale": None,
                    "meets": None,
                }
            )

    definite_results = [
        item["meets"]
        for item in assessments
        if item["meets"] is not None
    ]

    if definite_results and all(definite_results):
        status = "meets"

    elif definite_results and not any(definite_results):
        status = "does_not_meet"

    else:
        status = "unknown"

    return {
        "status": status,
        "student_cgpa": student_cgpa,
        "student_scale": student_scale,
        "requirements": assessments,
    }


# ============================================================
# DEADLINE
# ============================================================

def extract_deadline(text: str) -> str | None:
    """Try to detect a scholarship deadline."""
    patterns = [
        r"(?:deadline|application deadline|closing date|applications close)"
        r"[^A-Za-z0-9]{0,30}"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        r"(?:deadline|application deadline|closing date|applications close)"
        r"[^A-Za-z0-9]{0,30}"
        r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",

        r"(?:deadline|application deadline|closing date|applications close)"
        r"[^A-Za-z0-9]{0,30}"
        r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return clean_text(match.group(1))

    return None


# ============================================================
# SCHOLARSHIP MATCHING
# ============================================================

def calculate_match(
    *,
    title: str,
    url: str,
    h1s: list[str],
    h2s: list[str],
    h3s: list[str],
    text: str,
) -> dict:
    """Calculate a transparent scholarship match."""
    headings = h1s + h2s + h3s

    combined = " ".join(
        [title, url] + headings + [text]
    )

    scholarship_page = contains_any(
        combined,
        SCHOLARSHIP_SIGNALS,
    )

    degree = detect_degree_requirements(
        title,
        text,
    )

    field = detect_field_requirements(
        title,
        headings,
        text,
    )

    destinations = detect_destinations(
        title,
        url,
        text,
    )

    restricted_nationalities = find_restricted_nationalities(
        combined,
    )

    international = detect_international_eligibility(
        combined,
    )

    cgpa_requirements = extract_cgpa_requirements(
        text,
    )

    cgpa = cgpa_assessment(
        cgpa_requirements,
    )

    deadline = extract_deadline(
        text,
    )

    reasons = []
    warnings = []

    score = 0

    # --------------------------------------------------------
    # Scholarship signal
    # --------------------------------------------------------

    if scholarship_page:
        score += 10
        reasons.append(
            "Page contains scholarship/funding signals."
        )
    else:
        warnings.append(
            "Page does not clearly look like a scholarship page."
        )

    # --------------------------------------------------------
    # Degree
    # --------------------------------------------------------

    if degree["level"] == "Master's":
        score += 30
        reasons.append(
            "Master's-level scholarship signal detected."
        )

    elif degree["level"] == "Unknown":
        score += 5
        warnings.append(
            "Degree level could not be confirmed."
        )

    elif degree["level"] == "PhD":
        score -= 60
        warnings.append(
            "This appears to be a PhD/doctoral opportunity."
        )

    elif degree["level"] == "Bachelor's":
        score -= 60
        warnings.append(
            "This appears to be a Bachelor's/undergraduate opportunity."
        )

    else:
        score -= 40
        warnings.append(
            "The opportunity appears to target another degree/program."
        )

    # --------------------------------------------------------
    # Field
    # --------------------------------------------------------

    if field["matches_student_field"]:
        score += 25

        reasons.append(
            "Computer Science/IT-related field detected."
        )

    else:
        score -= 20

        warnings.append(
            "Computer Science/IT relevance could not be confirmed."
        )

    # --------------------------------------------------------
    # Nationality
    # --------------------------------------------------------

    if restricted_nationalities:
        # IMPORTANT:
        # We only penalize explicit restrictions.
        # Merely mentioning "Indian students" somewhere on a
        # page does NOT automatically make it India-only.
        score -= 70

        warnings.append(
            "Explicit nationality restriction detected: "
            + ", ".join(restricted_nationalities)
        )

    elif international:
        score += 20

        reasons.append(
            "International applicants/students are explicitly mentioned."
        )

    else:
        score += 5

        warnings.append(
            "Nationality eligibility is not explicit."
        )

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    preferred = []

    for destination in destinations:
        if destination.lower() in [
            item.lower()
            for item in STUDENT_PROFILE["preferred_destinations"]
        ]:
            preferred.append(destination)

    if preferred:
        score += 10

        reasons.append(
            "Preferred destination detected: "
            + ", ".join(preferred)
        )

    elif destinations:
        reasons.append(
            "Destination detected: "
            + ", ".join(destinations[:5])
        )

    else:
        warnings.append(
            "Destination could not be reliably detected."
        )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    if cgpa["status"] == "meets":
        score += 10

        reasons.append(
            "Current CGPA appears to meet detected requirement(s)."
        )

    elif cgpa["status"] == "does_not_meet":
        score -= 35

        warnings.append(
            "Current CGPA appears below at least one detected requirement."
        )

    else:
        warnings.append(
            "No comparable CGPA requirement was found."
        )

    # --------------------------------------------------------
    # Clamp score
    # --------------------------------------------------------

    score = max(0, min(100, score))

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if (
        restricted_nationalities
        or degree["level"] in {"PhD", "Bachelor's", "Other"}
        or cgpa["status"] == "does_not_meet"
    ):
        if score >= 70:
            status = "possible_match"
        else:
            status = "likely_not_eligible"

    elif score >= 80:
        status = "strong_match"

    elif score >= 65:
        status = "good_match"

    elif score >= 45:
        status = "possible_match"

    else:
        status = "likely_not_eligible"

    return {
        "match_score": score,
        "match_status": status,
        "reasons": reasons,
        "warnings": warnings,

        "cgpa_requirements": {
            "status": cgpa["status"],
            "detected": cgpa["requirements"],
            "student_cgpa": STUDENT_PROFILE["cgpa"],
            "student_scale": STUDENT_PROFILE["cgpa_scale"],
        },

        "nationality_requirements": {
            "student_nationality": STUDENT_PROFILE["nationality"],
            "international_students_detected": international,
            "explicit_restrictions": restricted_nationalities,
        },

        "degree_requirements": {
            "student_degree": STUDENT_PROFILE["degree_level"],
            "detected_level": degree["level"],
        },

        "field_requirements": {
            "student_field": STUDENT_PROFILE["field"],
            "matched_keywords": field["matched_keywords"],
            "matches_student_field": field["matches_student_field"],
        },

        "destination": {
            "detected": destinations,
            "preferred_matches": preferred,
        },

        "deadline": deadline,
    }


# ============================================================
# LINK FILTERING
# ============================================================

def should_follow_url(url: str) -> bool:
    """Decide whether a link is worth crawling."""
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = parsed.netloc.lower()

    # Keep this crawler focused on WeMakeScholars.
    if "wemakescholars.com" not in hostname:
        return False

    lower_url = url.lower()

    ignored_parts = [
        "/signup",
        "/login",
        "/referral",
        "/education-loan",
        "/blog",
        "/contact",
        "/about",
        "/privacy",
        "/terms",
        "/cookie",
    ]

    return not any(
        part in lower_url
        for part in ignored_parts
    )


# ============================================================
# REQUEST HANDLER
# ============================================================

@router.default_handler
async def default_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:
    """Process each crawled page."""
    url = context.request.url

    Actor.log.info(
        f"Processing scholarship page: {url}"
    )

    title = get_title(context)

    h1s, h2s, h3s = get_headings(context)

    text = page_text(context)

    match = calculate_match(
        title=title,
        url=url,
        h1s=h1s,
        h2s=h2s,
        h3s=h3s,
        text=text,
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    data = {
        "url": url,
        "title": title,

        "student_profile": {
            "nationality": STUDENT_PROFILE["nationality"],
            "date_of_birth": STUDENT_PROFILE["date_of_birth"],
            "cgpa": STUDENT_PROFILE["cgpa"],
            "cgpa_scale": STUDENT_PROFILE["cgpa_scale"],
            "degree_level": STUDENT_PROFILE["degree_level"],
            "field": STUDENT_PROFILE["field"],
            "preferred_destinations": (
                STUDENT_PROFILE["preferred_destinations"]
            ),
        },

        "match_status": match["match_status"],
        "match_score": match["match_score"],

        "reasons": match["reasons"],
        "warnings": match["warnings"],

        "cgpa_requirements": match[
            "cgpa_requirements"
        ],

        "nationality_requirements": match[
            "nationality_requirements"
        ],

        "degree_requirements": match[
            "degree_requirements"
        ],

        "field_requirements": match[
            "field_requirements"
        ],

        "destination": match[
            "destination"
        ],

        "deadline": match["deadline"],

        "source_domain": urlparse(url).netloc,

        "h1s": h1s,
        "h2s": h2s,
        "h3s": h3s,
    }

    # Save the result to Apify Dataset.
    await context.push_data(data)

    # --------------------------------------------------------
    # Continue crawling relevant pages
    # --------------------------------------------------------

    try:
        links = context.soup.find_all("a", href=True)

        urls_to_follow = []

        for link in links:
            href = link.get("href")

            if not href:
                continue

            absolute_url = (
                context.request.loaded_url
                if False
                else None
            )

            # Use Crawlee's own link handling below.
            # This loop is only used for logging/filtering.
            if should_follow_url(href):
                urls_to_follow.append(href)

        Actor.log.info(
            f"Found {len(urls_to_follow)} potentially relevant links."
        )

    except Exception as exc:
        Actor.log.warning(
            f"Could not inspect links: {exc}"
        )

    # Crawlee handles URL resolution and duplicate prevention.
    # Same-hostname is used so the crawler does not wander onto
    # unrelated websites.
    await context.enqueue_links(
        strategy="same-hostname",
    )
