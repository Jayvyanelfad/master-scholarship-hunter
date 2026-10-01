"""Scholarship crawler and student-profile matching logic."""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

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

    # Main study target
    "degree": "Master",
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
        "cyber security",
        "cybersecurity",
        "computer engineering",
        "informatics",
        "computing",
        "information technology",
        "IT",
    ],

    # Countries you are interested in.
    # Add/remove countries whenever you want.
    "preferred_destinations": [
        "Germany",
        "France",
        "Netherlands",
        "Belgium",
        "Finland",
        "Sweden",
        "Norway",
        "Denmark",
        "United Kingdom",
        "UK",
        "Ireland",
        "Canada",
        "Australia",
        "Austria",
        "Switzerland",
        "Luxembourg",
    ],
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    """Normalize whitespace."""
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def normalize(value: str | None) -> str:
    """Lowercase and normalize text for matching."""
    value = clean_text(value)
    return value.lower()


def unique_list(values: list[str]) -> list[str]:
    """Remove duplicate strings while preserving order."""
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def calculate_age(date_of_birth: str) -> int:
    """Calculate current age from YYYY-MM-DD."""
    dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    today = date.today()

    age = today.year - dob.year

    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1

    return age


def get_title(context: BeautifulSoupCrawlingContext) -> str:
    """Get the page title."""
    if not context.soup.title:
        return ""

    return clean_text(context.soup.title.get_text(" ", strip=True))


def get_headings(context: BeautifulSoupCrawlingContext) -> tuple[list[str], list[str], list[str]]:
    """Extract H1/H2/H3 headings."""
    h1s = unique_list(
        [h.get_text(" ", strip=True) for h in context.soup.find_all("h1")]
    )

    h2s = unique_list(
        [h.get_text(" ", strip=True) for h in context.soup.find_all("h2")]
    )

    h3s = unique_list(
        [h.get_text(" ", strip=True) for h in context.soup.find_all("h3")]
    )

    return h1s, h2s, h3s


def extract_relevant_text(
    context: BeautifulSoupCrawlingContext,
    title: str,
    h1s: list[str],
    h2s: list[str],
    h3s: list[str],
) -> str:
    """
    Build the text used for matching.

    We deliberately give much more importance to the title/headings
    than to arbitrary mentions elsewhere on the page.
    """

    body_text = context.soup.get_text(" ", strip=True)

    # Remove scripts/styles.
    for element in context.soup(["script", "style", "noscript"]):
        element.decompose()

    body_text = context.soup.get_text(" ", strip=True)

    focused_text = " ".join(
        [
            title,
            " ".join(h1s),
            " ".join(h2s),
            " ".join(h3s),
            body_text,
        ]
    )

    return clean_text(focused_text)


# ============================================================
# DEGREE DETECTION
# ============================================================

def detect_degree(text: str) -> str:
    """Detect the main academic level."""
    t = normalize(text)

    if re.search(r"\bph\.?d\b|\bdoctorate\b|\bdoctoral\b", t):
        return "PhD"

    if re.search(r"\bmaster'?s?\b|\bmsc\b|\bma\b|\bgraduate\b", t):
        return "Master"

    if re.search(r"\bbachelor'?s?\b|\bbsc\b|\bundergraduate\b", t):
        return "Bachelor"

    if re.search(r"\bmba\b", t):
        return "MBA"

    if re.search(r"\bmbbs\b|\bmedicine\b|\bmedical\b|\bmd\b", t):
        return "Medicine"

    return "Unknown"


# ============================================================
# FIELD DETECTION
# ============================================================

def detect_field(text: str) -> tuple[str, list[str]]:
    """Detect whether the scholarship is related to the target field."""
    t = normalize(text)

    found: list[str] = []

    for keyword in STUDENT_PROFILE["field_keywords"]:
        keyword_normalized = normalize(keyword)

        if keyword_normalized in t:
            found.append(keyword)

    found = unique_list(found)

    if found:
        return "Computer Science / IT related", found

    # Related technical fields.
    related_keywords = [
        "engineering",
        "technology",
        "digital",
        "mathematics",
        "statistics",
        "computational",
        "robotics",
        "electrical engineering",
    ]

    related_found = [
        keyword
        for keyword in related_keywords
        if keyword in t
    ]

    if related_found:
        return "Related technical field", unique_list(related_found)

    return "Unknown / not detected", []


# ============================================================
# DESTINATION DETECTION
# ============================================================

COUNTRIES = [
    "Germany",
    "France",
    "Netherlands",
    "Belgium",
    "Finland",
    "Sweden",
    "Norway",
    "Denmark",
    "United Kingdom",
    "UK",
    "Ireland",
    "Canada",
    "Australia",
    "Austria",
    "Switzerland",
    "Luxembourg",
    "United States",
    "USA",
    "United States of America",
    "Malaysia",
    "India",
    "Japan",
    "South Korea",
    "New Zealand",
    "Italy",
    "Spain",
    "Portugal",
    "Poland",
    "Hungary",
    "Czech Republic",
]


def detect_destinations(text: str) -> list[str]:
    """Find countries explicitly mentioned in the page."""
    t = normalize(text)

    found: list[str] = []

    for country in COUNTRIES:
        if normalize(country) in t:
            found.append(country)

    return unique_list(found)


# ============================================================
# NATIONALITY / ELIGIBILITY
# ============================================================

def detect_nationality_requirements(text: str) -> dict:
    """
    Detect explicit nationality restrictions.

    Important:
    A page mentioning 'Indian students' is NOT automatically treated
    as India-only. We only mark it as restrictive when the wording
    strongly indicates exclusivity.
    """

    t = normalize(text)

    requirements: list[str] = []
    warnings: list[str] = []

    # Strong India-only patterns.
    india_only_patterns = [
        r"\bindian citizens only\b",
        r"\bonly indian citizens\b",
        r"\bonly indian students\b",
        r"\bfor indian nationals only\b",
        r"\bapplicants must be indian\b",
        r"\bapplicant must be an indian\b",
        r"\bindian nationals only\b",
    ]

    india_only = any(
        re.search(pattern, t)
        for pattern in india_only_patterns
    )

    if india_only:
        requirements.append("Restricted to Indian applicants")
        warnings.append(
            "The page appears to explicitly restrict eligibility to Indian applicants."
        )

    # Benin / international eligibility.
    international_patterns = [
        r"\binternational students\b",
        r"\binternational applicants\b",
        r"\bstudents from all countries\b",
        r"\ball nationalities\b",
        r"\bany nationality\b",
        r"\bforeign students\b",
        r"\bnon[- ]eu students\b",
    ]

    if any(re.search(pattern, t) for pattern in international_patterns):
        requirements.append("International applicants mentioned")

    if "benin" in t or "beninese" in t:
        requirements.append("Benin / Beninese mentioned")

    return {
        "requirements": unique_list(requirements),
        "india_only": india_only,
        "warnings": unique_list(warnings),
    }


# ============================================================
# CGPA DETECTION
# ============================================================

def extract_cgpa_requirement(text: str) -> dict:
    """
    Extract common CGPA/GPA requirements.

    Examples detected:
      CGPA 3.0
      minimum CGPA of 3.5
      GPA of 3.0/4.0
      minimum 70%
    """

    t = normalize(text)

    patterns = [
        r"(?:minimum|min\.?)\s+(?:cgpa|gpa)\s*(?:of|:)?\s*(\d+(?:\.\d+)?)",
        r"(?:cgpa|gpa)\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*(?:/|out of)\s*(\d+(?:\.\d+)?)",
        r"(?:cgpa|gpa)\s*(?:requirement|required)\s*(?:of|:)?\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, t)

        if match:
            try:
                value = float(match.group(1))

                scale = None

                if match.lastindex and match.lastindex >= 2:
                    try:
                        scale = float(match.group(2))
                    except (TypeError, ValueError):
                        scale = None

                return {
                    "found": True,
                    "minimum": value,
                    "scale": scale,
                    "raw": clean_text(match.group(0)),
                }

            except (TypeError, ValueError):
                pass

    # Percentage requirements.
    percentage_patterns = [
        r"(?:minimum|min\.?)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%",
        r"(?:at least|minimum)\s*(\d+(?:\.\d+)?)\s*%",
    ]

    for pattern in percentage_patterns:
        match = re.search(pattern, t)

        if match:
            try:
                percentage = float(match.group(1))

                return {
                    "found": True,
                    "minimum": percentage,
                    "scale": 100.0,
                    "raw": clean_text(match.group(0)),
                }

            except (TypeError, ValueError):
                pass

    return {
        "found": False,
        "minimum": None,
        "scale": None,
        "raw": None,
    }


# ============================================================
# DEADLINE
# ============================================================

def extract_deadlines(text: str) -> list[str]:
    """Extract common deadline/date expressions."""
    patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
    ]

    found: list[str] = []

    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.IGNORECASE))

    return unique_list(found)[:10]


# ============================================================
# MATCHING ENGINE
# ============================================================

def build_match(text: str, title: str, url: str) -> dict:
    """Score a scholarship against the student's profile."""

    normalized_title = normalize(title)
    normalized_text = normalize(text)

    reasons: list[str] = []
    warnings: list[str] = []

    score = 0

    # --------------------------------------------------------
    # DEGREE
    # --------------------------------------------------------

    degree = detect_degree(
        f"{title} {text[:5000]}"
    )

    if degree == "Master":
        score += 30
        reasons.append("Master's-level opportunity detected.")

    elif degree == "PhD":
        score -= 45
        warnings.append("This appears to be a PhD/doctoral opportunity.")

    elif degree == "Bachelor":
        score -= 45
        warnings.append("This appears to be a Bachelor's opportunity.")

    elif degree == "MBA":
        score -= 35
        warnings.append("This appears to be an MBA opportunity.")

    elif degree == "Medicine":
        score -= 45
        warnings.append("This appears to be a medicine/medical opportunity.")

    else:
        warnings.append("Academic level could not be confirmed.")

    # --------------------------------------------------------
    # FIELD
    # --------------------------------------------------------

    field, field_matches = detect_field(
        f"{title} {text[:12000]}"
    )

    if field == "Computer Science / IT related":
        score += 30
        reasons.append(
            f"Computer Science/IT field detected: {', '.join(field_matches[:5])}."
        )

    elif field == "Related technical field":
        score += 12
        reasons.append(
            f"Related technical field detected: {', '.join(field_matches[:5])}."
        )

    else:
        score -= 15
        warnings.append(
            "Computer Science / IT relevance was not clearly detected."
        )

    # --------------------------------------------------------
    # NATIONALITY
    # --------------------------------------------------------

    nationality = detect_nationality_requirements(
        f"{title} {text}"
    )

    nationality_requirements = nationality["requirements"]

    if nationality["india_only"]:
        score -= 60
        warnings.append(
            "This appears to be restricted to Indian applicants."
        )

    elif any(
        phrase in normalize(" ".join(nationality_requirements))
        for phrase in [
            "international applicants",
            "international students",
            "all countries",
            "any nationality",
            "foreign students",
        ]
    ):
        score += 20
        reasons.append(
            "International eligibility is explicitly mentioned."
        )

    elif "benin / beninese mentioned" in [
        normalize(x)
        for x in nationality_requirements
    ]:
        score += 20
        reasons.append(
            "Benin/Beninese eligibility is explicitly mentioned."
        )

    else:
        warnings.append(
            "Nationality eligibility could not be confirmed from the page."
        )

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    destinations = detect_destinations(
        f"{title} {text[:8000]}"
    )

    preferred = STUDENT_PROFILE["preferred_destinations"]

    preferred_found = [
        country
        for country in destinations
        if country in preferred
    ]

    if preferred_found:
        score += 10
        reasons.append(
            "Preferred destination detected: "
            + ", ".join(preferred_found[:5])
            + "."
        )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    cgpa_info = extract_cgpa_requirement(
        f"{title} {text}"
    )

    if cgpa_info["found"]:
        minimum = cgpa_info["minimum"]
        scale = cgpa_info["scale"]

        # If scholarship uses the same 10-point scale.
        if scale == 10.0:
            if STUDENT_PROFILE["cgpa"] >= minimum:
                score += 15
                reasons.append(
                    f"CGPA {STUDENT_PROFILE['cgpa']:.1f}/10 meets "
                    f"the detected minimum of {minimum:.1f}/10."
                )
            else:
                score -= 35
                warnings.append(
                    f"Detected minimum CGPA {minimum:.1f}/10 is above "
                    f"your CGPA of {STUDENT_PROFILE['cgpa']:.1f}/10."
                )

        # 4-point scale.
        elif scale == 4.0:
            user_equivalent = (
                STUDENT_PROFILE["cgpa"]
                / STUDENT_PROFILE["cgpa_scale"]
                * 4
            )

            if user_equivalent >= minimum:
                score += 15
                reasons.append(
                    f"Your approximate equivalent GPA ({user_equivalent:.2f}/4) "
                    f"meets the detected minimum of {minimum:.2f}/4."
                )
            else:
                score -= 35
                warnings.append(
                    f"Detected minimum GPA {minimum:.2f}/4 may exceed "
                    f"your approximate equivalent GPA ({user_equivalent:.2f}/4)."
                )

        else:
            warnings.append(
                f"Detected academic requirement: {cgpa_info['raw']} "
                "(scale could not be reliably determined)."
            )

    else:
        warnings.append(
            "No clear CGPA/GPA requirement was detected."
        )

    # --------------------------------------------------------
    # AGE
    # --------------------------------------------------------

    try:
        age = calculate_age(
            STUDENT_PROFILE["date_of_birth"]
        )
    except ValueError:
        age = None

    # Basic age-limit detection.
    age_patterns = [
        r"(?:maximum|max\.?|under)\s+age\s*(?:of|:)?\s*(\d{2})",
        r"age\s*(?:limit|requirement)\s*(?:of|:)?\s*(\d{2})",
        r"must\s+be\s+(?:under|below)\s+(\d{2})",
    ]

    age_limit = None

    for pattern in age_patterns:
        match = re.search(pattern, normalized_text)

        if match:
            try:
                age_limit = int(match.group(1))
                break
            except ValueError:
                pass

    if age is not None and age_limit is not None:
        if age < age_limit:
            score += 5
            reasons.append(
                f"Age {age} appears to satisfy the detected age limit of {age_limit}."
            )
        else:
            score -= 25
            warnings.append(
                f"Current age {age} may exceed the detected age limit of {age_limit}."
            )

    # --------------------------------------------------------
    # URL / TITLE QUALITY
    # --------------------------------------------------------

    scholarship_signal = any(
        word in normalized_title
        for word in [
            "scholarship",
            "fellowship",
            "grant",
            "funding",
        ]
    )

    if scholarship_signal:
        score += 5
        reasons.append("Scholarship/funding opportunity detected.")

    # --------------------------------------------------------
    # SCORE NORMALIZATION
    # --------------------------------------------------------

    score = max(0, min(100, score))

    # Important:
    # "likely_not_eligible" is reserved for strong negative evidence.
    strong_negative = (
        nationality["india_only"]
        or degree in {"PhD", "Bachelor", "MBA", "Medicine"}
    )

    if strong_negative or score < 25:
        match_status = "likely_not_eligible"

    elif score >= 75:
        match_status = "strong_match"

    elif score >= 55:
        match_status = "good_match"

    elif score >= 35:
        match_status = "possible_match"

    else:
        match_status = "needs_manual_check"

    # Remove duplicates.
    reasons = unique_list(reasons)
    warnings = unique_list(warnings)

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {
        "match_score": score,
        "match_status": match_status,
        "reasons": reasons[:8],
        "warnings": warnings[:8],

        "student_profile": {
            "nationality": STUDENT_PROFILE["nationality"],
            "date_of_birth": STUDENT_PROFILE["date_of_birth"],
            "age": age,
            "degree": STUDENT_PROFILE["degree"],
            "field": STUDENT_PROFILE["field"],
            "cgpa": STUDENT_PROFILE["cgpa"],
            "cgpa_scale": STUDENT_PROFILE["cgpa_scale"],
        },

        "degree_requirements": {
            "detected_degree": degree,
            "target_degree": STUDENT_PROFILE["degree"],
        },

        "field_requirements": {
            "detected_field": field,
            "matched_keywords": field_matches,
            "target_field": STUDENT_PROFILE["field"],
        },

        "nationality_requirements": nationality_requirements,

        "cgpa_requirements": cgpa_info,

        "destination": {
            "detected": destinations,
            "preferred_found": preferred_found,
        },

        "deadlines": extract_deadlines(text),
    }


# ============================================================
# CRAWLER
# ============================================================

@router.default_handler
async def default_handler(context: BeautifulSoupCrawlingContext) -> None:
    """Extract scholarship information and follow useful links."""

    url = context.request.url

    Actor.log.info(f"Scraping: {url}")

    title = get_title(context)

    h1s, h2s, h3s = get_headings(context)

    # Create matching text.
    text = extract_relevant_text(
        context,
        title,
        h1s,
        h2s,
        h3s,
    )

    # Score this page.
    match = build_match(
        text=text,
        title=title,
        url=url,
    )

    # Source domain.
    source_domain = urlparse(url).netloc

    # Final output.
    data = {
        "url": url,
        "title": title,

        "match_score": match["match_score"],
        "match_status": match["match_status"],

        "reasons": match["reasons"],
        "warnings": match["warnings"],

        "student_profile": match["student_profile"],

        "degree_requirements": match["degree_requirements"],
        "field_requirements": match["field_requirements"],
        "nationality_requirements": match["nationality_requirements"],
        "cgpa_requirements": match["cgpa_requirements"],

        "destination": match["destination"],
        "deadlines": match["deadlines"],

        "source_domain": source_domain,

        "h1s": h1s,
        "h2s": h2s,
        "h3s": h3s,
    }

    await context.push_data(data)

    # ========================================================
    # ONLY FOLLOW USEFUL SCHOLARSHIP LINKS
    # ========================================================

    include_patterns = [
        re.compile(
            r".*(scholarship|fellowship|funding|grant|masters|master|"
            r"computer-science|information-technology|information-technology|"
            r"study-abroad).*",
            re.IGNORECASE,
        )
    ]

    exclude_patterns = [
        re.compile(r".*(facebook|instagram|twitter|linkedin|youtube).*", re.I),
        re.compile(r".*\.(pdf|jpg|jpeg|png|gif|zip)$", re.I),
        re.compile(r".*(login|signup|register|referral).*", re.I),
    ]

    try:
        await context.enqueue_links(
            strategy="same-hostname",
            include=include_patterns,
            exclude=exclude_patterns,
            limit=25,
        )

    except Exception as exc:
        Actor.log.warning(
            f"Could not enqueue links from {url}: {exc}"
        )
