from __future__ import annotations

import re
from datetime import datetime
from typing import Any
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
    "degree": "Master",
    "field": "Computer Science",

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


MAX_SCHOLARSHIP_LINKS = 40


# ============================================================
# HELPERS
# ============================================================

def clean(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def norm(value: str | None) -> str:
    return clean(value).lower()


def unique(values: list[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        value = clean(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def get_title(
    context: BeautifulSoupCrawlingContext,
) -> str:

    title = context.soup.find("title")

    if title:
        value = clean(title.get_text())

        if value:
            return value

    h1 = context.soup.find("h1")

    if h1:
        value = clean(h1.get_text())

        if value:
            return value

    return "Unknown scholarship"


def get_headings(
    context: BeautifulSoupCrawlingContext,
):

    h1s = unique([
        clean(x.get_text())
        for x in context.soup.find_all("h1")
    ])

    h2s = unique([
        clean(x.get_text())
        for x in context.soup.find_all("h2")
    ])

    h3s = unique([
        clean(x.get_text())
        for x in context.soup.find_all("h3")
    ])

    return h1s, h2s, h3s


def get_text(
    context: BeautifulSoupCrawlingContext,
) -> str:

    soup = context.soup

    for tag in soup.find_all(
        ["script", "style", "noscript", "svg", "iframe"]
    ):
        tag.decompose()

    return clean(
        soup.get_text(" ", strip=True)
    )


# ============================================================
# URL DETECTION
# ============================================================

def is_scholarship_url(url: str) -> bool:

    parsed = urlparse(url)

    if parsed.netloc.lower() not in {
        "www.wemakescholars.com",
        "wemakescholars.com",
    }:
        return False

    return bool(
        re.fullmatch(
            r"/scholarship/[^/?#]+/?",
            parsed.path,
            re.IGNORECASE,
        )
    )


# ============================================================
# WE MAKE SCHOLARS FIELD EXTRACTION
# ============================================================

FIELD_NAMES = [
    "Eligible Degrees",
    "Funding Type",
    "Deadline",
    "Provider",
    "Eligible Courses",
    "Eligible Nationalities",
    "Scholarship can be taken at",
    "Can Be Taken At",
    "Study At",
    "Last Verified On",
    "Overview",
    "Scholarship Details",
]


def extract_field(
    text: str,
    field_name: str,
) -> str:

    """
    Extract only the value between one WMS field label
    and the next WMS field label.

    Example:

    Eligible Degrees:
    Masters

    Funding Type:
    Partial Funding

    Deadline:
    31 Oct, 2026

    returns only:

    Masters
    """

    escaped_fields = "|".join(
        re.escape(x)
        for x in FIELD_NAMES
    )

    pattern = re.compile(
        rf"{re.escape(field_name)}"
        rf"\s*:?\s*"
        rf"(.*?)"
        rf"(?="
        rf"\s*(?:{escaped_fields})"
        rf"\s*:?"
        rf"|\s*Overview"
        rf"|$"
        rf")",
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(text)

    if not match:
        return ""

    value = clean(match.group(1))

    # Remove common navigation junk.
    value = re.sub(
        r"\b(Shortlist|More Details|Apply Now)\b",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return clean(value)


def extract_degree(
    text: str,
) -> str:

    return extract_field(
        text,
        "Eligible Degrees",
    )


def extract_courses(
    text: str,
) -> str:

    return extract_field(
        text,
        "Eligible Courses",
    )


def extract_nationality(
    text: str,
) -> str:

    return extract_field(
        text,
        "Eligible Nationalities",
    )


def extract_destination(
    text: str,
) -> str:

    value = extract_field(
        text,
        "Scholarship can be taken at",
    )

    if not value:

        value = extract_field(
            text,
            "Can Be Taken At",
        )

    if not value:

        value = extract_field(
            text,
            "Study At",
        )

    return value


def extract_deadline(
    text: str,
) -> str:

    return extract_field(
        text,
        "Deadline",
    )


def extract_funding(
    text: str,
) -> str:

    return extract_field(
        text,
        "Funding Type",
    )


# ============================================================
# DEGREE
# ============================================================

def master_match(
    title: str,
    degree: str,
) -> tuple[bool, bool]:

    combined = norm(
        f"{title} {degree}"
    )

    master = bool(
        re.search(
            r"\bmasters?\b"
            r"|\bmaster'?s\b"
            r"|\bmsc\b"
            r"|\bm\.sc\b",
            combined,
        )
    )

    bachelor = bool(
        re.search(
            r"\bbachelors?\b"
            r"|\bbachelor'?s\b"
            r"|\bbsc\b",
            combined,
        )
    )

    phd = bool(
        re.search(
            r"\bphd\b"
            r"|\bph\.d\b"
            r"|\bdoctorate\b",
            combined,
        )
    )

    if master:
        return True, False

    if bachelor or phd:
        return False, True

    return False, False


# ============================================================
# FIELD
# ============================================================

def field_match(
    title: str,
    courses: str,
) -> tuple[bool, bool]:

    text = norm(
        f"{title} {courses}"
    )

    strong = [
        "computer science",
        "computer sciences",
        "information technology",
        "information systems",
        "software engineering",
        "computer engineering",
        "informatics",
        "computing",
    ]

    related = [
        "data science",
        "artificial intelligence",
        "machine learning",
        "cyber security",
        "cybersecurity",
        "data engineering",
        "software development",
    ]

    direct = any(
        x in text
        for x in strong
    )

    related_match = any(
        x in text
        for x in related
    )

    # Safe IT detection.
    if re.search(
        r"\bit\b",
        text,
    ):
        direct = True

    return direct, related_match


# ============================================================
# NATIONALITY
# ============================================================

def nationality_match(
    nationality: str,
) -> tuple[str, bool]:

    text = norm(nationality)

    if not text:
        return "unknown", False

    if any(
        phrase in text
        for phrase in [
            "open to all nationals",
            "all nationals",
            "all nationalities",
            "open to international students",
            "international students",
            "any nationality",
        ]
    ):
        return "eligible", False

    if (
        "benin" in text
        or "beninese" in text
        or "african nationals" in text
        or "african students" in text
        or "students from africa" in text
    ):
        return "eligible", False

    india_only = [
        "indian nationals only",
        "indian citizens only",
        "only indian nationals",
        "only indian citizens",
        "open to indian nationals only",
        "open to indian citizens only",
    ]

    if any(
        x in text
        for x in india_only
    ):
        return "excluded", True

    # If it says Indian students but doesn't explicitly say only,
    # do not automatically reject.
    if "indian" in text or "india" in text:
        return "unknown", False

    return "unknown", False


# ============================================================
# CGPA
# ============================================================

def extract_cgpa(
    text: str,
) -> list[str]:

    patterns = [
        r"(?:minimum|min|required|at least)"
        r"\s*(?:cgpa|gpa)"
        r"\s*(?:of|:)?\s*"
        r"\d+(?:\.\d+)?"
        r"(?:\s*(?:/|out of)\s*\d+(?:\.\d+)?)?",

        r"\b(?:cgpa|gpa)"
        r"\s*(?:of|:)?\s*"
        r"\d+(?:\.\d+)?"
        r"(?:\s*(?:/|out of)\s*\d+(?:\.\d+)?)?",

        r"\bminimum\s+\d+(?:\.\d+)?\s*%",
    ]

    results = []

    for pattern in patterns:

        for match in re.findall(
            pattern,
            text,
            re.IGNORECASE,
        ):

            match = clean(match)

            if match and match not in results:
                results.append(match)

    return results[:10]


def cgpa_check(
    requirements: list[str],
) -> tuple[str, list[str]]:

    if not requirements:
        return (
            "unknown",
            ["No specific CGPA requirement detected."],
        )

    applicant = (
        STUDENT_PROFILE["cgpa"]
        / STUDENT_PROFILE["cgpa_scale"]
    )

    for requirement in requirements:

        text = norm(requirement)

        match = re.search(
            r"(\d+(?:\.\d+)?)"
            r"\s*(?:/|out of)"
            r"\s*(\d+(?:\.\d+)?)",
            text,
        )

        if match:

            required = float(
                match.group(1)
            )

            scale = float(
                match.group(2)
            )

            if applicant >= required / scale:

                return (
                    "eligible",
                    [
                        f"CGPA {STUDENT_PROFILE['cgpa']}/"
                        f"{STUDENT_PROFILE['cgpa_scale']} "
                        f"meets {requirement}."
                    ],
                )

            return (
                "excluded",
                [
                    f"CGPA {STUDENT_PROFILE['cgpa']}/"
                    f"{STUDENT_PROFILE['cgpa_scale']} "
                    f"is below {requirement}."
                ],
            )

    return (
        "unknown",
        ["CGPA requirement could not be interpreted."],
    )


# ============================================================
# DESTINATION
# ============================================================

def destination_match(
    destination: str,
) -> bool:

    text = norm(destination)

    return any(
        norm(country) in text
        for country in STUDENT_PROFILE[
            "preferred_destinations"
        ]
    )


# ============================================================
# DEADLINE
# ============================================================

def deadline_expired(
    deadline: str,
) -> bool:

    if not deadline:
        return False

    formats = [
        "%d %b, %Y",
        "%d %B, %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
    ]

    for fmt in formats:

        try:

            date = datetime.strptime(
                deadline.strip(),
                fmt,
            )

            return (
                date.date()
                < datetime.now().date()
            )

        except ValueError:
            continue

    if "expired" in norm(deadline):
        return True

    return False


# ============================================================
# MATCH ENGINE
# ============================================================

def calculate_match(
    title: str,
    degree: str,
    courses: str,
    nationality: str,
    destination: str,
    deadline: str,
    cgpa_requirements: list[str],
    funding: str,
) -> dict[str, Any]:

    score = 0

    reasons = []
    warnings = []

    # --------------------------------------------------------
    # DEGREE
    # --------------------------------------------------------

    is_master, wrong_degree = master_match(
        title,
        degree,
    )

    if is_master:

        score += 35

        reasons.append(
            "Master's degree eligibility detected."
        )

    elif wrong_degree:

        score -= 50

        warnings.append(
            "This scholarship appears to target "
            "a different degree level."
        )

    else:

        warnings.append(
            "Master's eligibility is unclear."
        )

    # --------------------------------------------------------
    # FIELD
    # --------------------------------------------------------

    direct_field, related_field = field_match(
        title,
        courses,
    )

    if direct_field:

        score += 35

        reasons.append(
            "Computer Science / IT field match detected."
        )

    elif related_field:

        score += 20

        reasons.append(
            "Related technology field detected."
        )

    else:

        score -= 20

        warnings.append(
            "Computer Science / IT field match not detected."
        )

    # --------------------------------------------------------
    # NATIONALITY
    # --------------------------------------------------------

    nationality_status, nationality_excluded = (
        nationality_match(
            nationality
        )
    )

    if nationality_status == "eligible":

        score += 20

        reasons.append(
            "Nationality appears eligible."
        )

    elif nationality_excluded:

        score -= 60

        warnings.append(
            "Nationality restriction appears incompatible "
            "with a Benin applicant."
        )

    else:

        warnings.append(
            "Nationality eligibility needs manual confirmation."
        )

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    if destination_match(
        destination
    ):

        score += 10

        reasons.append(
            "Destination matches one of your preferred countries."
        )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    cgpa_status, cgpa_messages = cgpa_check(
        cgpa_requirements
    )

    if cgpa_status == "eligible":

        score += 10
        reasons.extend(cgpa_messages)

    elif cgpa_status == "excluded":

        score -= 35
        warnings.extend(cgpa_messages)

    else:

        # IMPORTANT:
        # Unknown CGPA should NOT punish the scholarship.
        warnings.extend(cgpa_messages)

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if funding:

        score += 5

        reasons.append(
            f"Funding information: {funding}"
        )

    # --------------------------------------------------------
    # DEADLINE
    # --------------------------------------------------------

    if deadline:

        if deadline_expired(deadline):

            score -= 20

            warnings.append(
                f"Deadline appears expired: {deadline}"
            )

        else:

            reasons.append(
                f"Deadline: {deadline}"
            )

    else:

        warnings.append(
            "No clear deadline detected."
        )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if wrong_degree:
        status = "likely_not_eligible"

    elif nationality_excluded:
        status = "likely_not_eligible"

    elif cgpa_status == "excluded":
        status = "likely_not_eligible"

    elif score >= 75:
        status = "strong_match"

    elif score >= 55:
        status = "good_match"

    elif score >= 35:
        status = "possible_match"

    elif score >= 20:
        status = "needs_manual_check"

    else:
        status = "likely_not_eligible"

    return {
        "match_score": score,
        "match_status": status,
        "reasons": unique(reasons),
        "warnings": unique(warnings),
    }


# ============================================================
# LISTING PAGE
# ============================================================

async def process_listing(
    context: BeautifulSoupCrawlingContext,
) -> None:

    found = []

    for link in context.soup.find_all(
        "a",
        href=True,
    ):

        href = link.get("href")

        if not isinstance(
            href,
            str,
        ):
            continue

        url = urljoin(
            context.request.url,
            href,
        )

        parsed = urlparse(url)

        if parsed.netloc.lower() not in {
            "www.wemakescholars.com",
            "wemakescholars.com",
        }:
            continue

        clean_url = (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{parsed.path}"
        )

        if not is_scholarship_url(
            clean_url
        ):
            continue

        if clean_url not in found:
            found.append(clean_url)

        if len(found) >= MAX_SCHOLARSHIP_LINKS:
            break

    Actor.log.info(
        f"Found {len(found)} scholarship pages."
    )

    if found:

        # Crawlee 1.10.3 expects URL strings.
        await context.add_requests(found)

        Actor.log.info(
            f"Queued {len(found)} scholarship pages."
        )


# ============================================================
# SCHOLARSHIP PAGE
# ============================================================

async def process_scholarship(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    title = get_title(
        context
    )

    h1s, h2s, h3s = get_headings(
        context
    )

    text = get_text(
        context
    )

    # --------------------------------------------------------
    # EXTRACT EXACT FIELDS
    # --------------------------------------------------------

    degree = extract_degree(
        text
    )

    funding = extract_funding(
        text
    )

    deadline = extract_deadline(
        text
    )

    courses = extract_courses(
        text
    )

    nationality = extract_nationality(
        text
    )

    destination = extract_destination(
        text
    )

    cgpa_requirements = extract_cgpa(
        text
    )

    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

    match = calculate_match(
        title=title,
        degree=degree,
        courses=courses,
        nationality=nationality,
        destination=destination,
        deadline=deadline,
        cgpa_requirements=cgpa_requirements,
        funding=funding,
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    record = {
        "record_type": "individual_scholarship",

        "title": title,

        "url": url,

        "source_domain": urlparse(
            url
        ).netloc,

        "match_score": match[
            "match_score"
        ],

        "match_status": match[
            "match_status"
        ],

        "reasons": match[
            "reasons"
        ],

        "warnings": match[
            "warnings"
        ],

        "student_profile": STUDENT_PROFILE,

        "degree_requirements": {
            "raw": degree,
            "target": "Master",
        },

        "field_requirements": {
            "raw": courses,
            "target": "Computer Science / IT",
        },

        "nationality_requirements": {
            "raw": nationality,
            "student_nationality": "Benin",
        },

        "cgpa_requirements": cgpa_requirements,

        "destination": destination,

        "deadlines": (
            [deadline]
            if deadline
            else []
        ),

        "deadline_status": (
            "expired"
            if deadline_expired(deadline)
            else "active_or_unknown"
        ),

        "funding": funding,

        "h1s": h1s,

        "h2s": h2s,

        "h3s": h3s,
    }

    await context.push_data(
        record
    )

    Actor.log.info(
        f"RESULT | {title} | "
        f"{match['match_score']} | "
        f"{match['match_status']}"
    )


# ============================================================
# ROUTER
# ============================================================

@router.default_handler
async def default_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    if is_scholarship_url(url):

        await process_scholarship(
            context
        )

    else:

        await process_listing(
            context
        )
