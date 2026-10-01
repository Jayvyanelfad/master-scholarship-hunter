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
# YOUR SCHOLARSHIP PROFILE
# ============================================================

STUDENT_PROFILE = {
    "nationality": "Benin",
    "country": "Benin",
    "date_of_birth": "2002-03-13",
    "cgpa": 6.0,
    "cgpa_scale": 10.0,
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
# SETTINGS
# ============================================================

MAX_SCHOLARSHIP_LINKS_PER_PAGE = 40

SCHOLARSHIP_PATH_PATTERN = re.compile(
    r"^/scholarship/[^/?#]+/?$",
    re.IGNORECASE,
)

LISTING_WORDS = (
    "scholarship",
    "scholarships",
    "masters-scholarships",
    "phd-scholarships",
    "bachelors-scholarships",
)

FUNDING_KEYWORDS = (
    "full funding",
    "fully funded",
    "partial funding",
    "tuition fee",
    "tuition fees",
    "stipend",
    "scholarship amount",
    "funding type",
    "financial support",
    "award",
    "grant",
    "fellowship",
)


# ============================================================
# BASIC TEXT HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize(value: str | None) -> str:
    return clean_text(value).lower()


def unique_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def get_page_text(
    context: BeautifulSoupCrawlingContext,
) -> str:

    soup = context.soup

    # Work on a copy-like parsing context by removing
    # non-readable elements.
    for tag in soup.find_all(
        ["script", "style", "noscript", "svg", "iframe"]
    ):
        tag.decompose()

    return clean_text(
        soup.get_text(" ", strip=True)
    )


def get_multiline_text(
    context: BeautifulSoupCrawlingContext,
) -> str:

    soup = context.soup

    for tag in soup.find_all(
        ["script", "style", "noscript", "svg", "iframe"]
    ):
        tag.decompose()

    return soup.get_text("\n", strip=True)


def get_title(
    context: BeautifulSoupCrawlingContext,
) -> str:

    title_tag = context.soup.find("title")

    if title_tag:
        title = clean_text(title_tag.get_text())

        if title:
            return title

    h1 = context.soup.find("h1")

    if h1:
        title = clean_text(h1.get_text())

        if title:
            return title

    return "Unknown scholarship"


def get_headings(
    context: BeautifulSoupCrawlingContext,
) -> tuple[list[str], list[str], list[str]]:

    h1s = unique_list(
        [
            clean_text(x.get_text())
            for x in context.soup.find_all("h1")
        ]
    )

    h2s = unique_list(
        [
            clean_text(x.get_text())
            for x in context.soup.find_all("h2")
        ]
    )

    h3s = unique_list(
        [
            clean_text(x.get_text())
            for x in context.soup.find_all("h3")
        ]
    )

    return h1s, h2s, h3s


# ============================================================
# URL DETECTION
# ============================================================

def is_scholarship_detail_url(url: str) -> bool:

    parsed = urlparse(url)

    if parsed.netloc.lower() not in {
        "www.wemakescholars.com",
        "wemakescholars.com",
    }:
        return False

    path = parsed.path.lower()

    return bool(
        SCHOLARSHIP_PATH_PATTERN.fullmatch(path)
    )


def is_listing_page(url: str) -> bool:

    if is_scholarship_detail_url(url):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()

    return any(
        word in path
        for word in LISTING_WORDS
    )


# ============================================================
# SECTION EXTRACTION
# ============================================================

def extract_section(
    text: str,
    start_labels: list[str],
    end_labels: list[str],
) -> str:

    if not text:
        return ""

    start_pattern = "|".join(
        re.escape(label)
        for label in start_labels
    )

    end_pattern = "|".join(
        re.escape(label)
        for label in end_labels
    )

    pattern = re.compile(
        rf"(?:{start_pattern})"
        rf"\s*:?\s*(.*?)"
        rf"(?=\s*(?:{end_pattern})"
        rf"\s*:?\s*|$)",
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(text)

    if not match:
        return ""

    return clean_text(match.group(1))


def extract_degree_requirements(
    text: str,
) -> str:

    return extract_section(
        text,
        [
            "Eligible Degrees",
            "Eligible Degree",
        ],
        [
            "Funding Type",
            "Eligible Courses",
            "Deadline",
            "Eligible Nationalities",
            "Can Be Taken At",
            "Provider",
            "Overview",
            "Scholarship Details",
            "Last Verified On",
        ],
    )


def extract_field_requirements(
    text: str,
) -> str:

    return extract_section(
        text,
        [
            "Eligible Courses",
            "Eligible Course",
        ],
        [
            "Deadline",
            "Eligible Nationalities",
            "Can Be Taken At",
            "Provider",
            "Last Verified On",
            "Overview",
            "Scholarship Details",
            "Eligible Degrees",
            "Funding Type",
        ],
    )


def extract_nationality_requirements(
    text: str,
) -> str:

    return extract_section(
        text,
        [
            "Eligible Nationalities",
            "Eligible Nationality",
        ],
        [
            "Can Be Taken At",
            "Provider",
            "Last Verified On",
            "Overview",
            "Scholarship Details",
            "Eligible Degrees",
            "Funding Type",
            "Eligible Courses",
            "Deadline",
        ],
    )


def extract_destination(
    text: str,
) -> str:

    return extract_section(
        text,
        [
            "Can Be Taken At",
            "Study At",
            "Scholarship can be taken at",
        ],
        [
            "Provider",
            "Last Verified On",
            "Overview",
            "Scholarship Details",
            "Eligible Degrees",
            "Funding Type",
            "Eligible Courses",
            "Deadline",
            "Eligible Nationalities",
        ],
    )


# ============================================================
# DEADLINE EXTRACTION
# ============================================================

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)

DEADLINE_PATTERN = re.compile(
    rf"\b("
    rf"(?:0?[1-9]|[12]\d|3[01])"
    rf"(?:st|nd|rd|th)?"
    rf"\s+(?:{MONTHS})\s+\d{{4}}"
    rf"|"
    rf"(?:{MONTHS})\s+"
    rf"(?:0?[1-9]|[12]\d|3[01])"
    rf"(?:st|nd|rd|th)?"
    rf"[,]?\s+\d{{4}}"
    rf"|"
    rf"(?:0?[1-9]|[12]\d|3[01])"
    rf"[-/]"
    rf"(?:0?[1-9]|1[0-2])"
    rf"[-/]"
    rf"\d{{4}}"
    rf")\b",
    re.IGNORECASE,
)


def extract_deadlines(
    text: str,
) -> list[str]:

    matches = DEADLINE_PATTERN.findall(text)

    result: list[str] = []

    for item in matches:

        item = clean_text(item)

        if item and item not in result:
            result.append(item)

    return result[:10]


def deadline_is_expired(
    deadlines: list[str],
) -> bool:

    if not deadlines:
        return False

    now = datetime.now()

    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ]

    parsed_dates = []

    for raw_date in deadlines:

        cleaned = re.sub(
            r"(st|nd|rd|th)",
            "",
            raw_date,
            flags=re.IGNORECASE,
        )

        for fmt in formats:

            try:
                parsed_dates.append(
                    datetime.strptime(
                        cleaned,
                        fmt,
                    )
                )
                break

            except ValueError:
                continue

    if not parsed_dates:
        return False

    return all(
        date.date() < now.date()
        for date in parsed_dates
    )


# ============================================================
# AGE
# ============================================================

def calculate_age(
    date_of_birth: str,
) -> int:

    dob = datetime.strptime(
        date_of_birth,
        "%Y-%m-%d",
    ).date()

    today = datetime.now().date()

    age = today.year - dob.year

    if (today.month, today.day) < (
        dob.month,
        dob.day,
    ):
        age -= 1

    return age


# ============================================================
# DEGREE MATCHING
# ============================================================

def degree_matches_master(
    degree_text: str,
) -> tuple[bool, bool]:

    text = normalize(degree_text)

    master_found = bool(
        re.search(
            r"\bmasters?\b"
            r"|\bmaster'?s\b"
            r"|\bmsc\b"
            r"|\bm\.sc\b"
            r"|\bma\b",
            text,
        )
    )

    conflicting_degree = bool(
        re.search(
            r"\bphd\b"
            r"|\bph\.d\b"
            r"|\bdoctorate\b"
            r"|\bbachelors?\b"
            r"|\bbachelor'?s\b"
            r"|\bmbbs\b"
            r"|\bmedicine\b",
            text,
        )
    )

    return (
        master_found,
        conflicting_degree,
    )


# ============================================================
# FIELD MATCHING
# ============================================================

def field_matches(
    text: str,
) -> tuple[bool, bool]:

    text_normalized = normalize(text)

    strong_keywords = [
        "computer science",
        "computer sciences",
        "information technology",
        "information systems",
        "software engineering",
        "computer engineering",
        "informatics",
        "computing",
    ]

    related_keywords = [
        "data science",
        "artificial intelligence",
        "machine learning",
        "cyber security",
        "cybersecurity",
        "data engineering",
        "software development",
        "technology",
    ]

    strong_match = any(
        keyword in text_normalized
        for keyword in strong_keywords
    )

    related_match = any(
        keyword in text_normalized
        for keyword in related_keywords
    )

    # IMPORTANT:
    # Use a word boundary for IT.
    # Otherwise "it" matches inside words such as
    # "international".
    if re.search(
        r"\bit\b",
        text_normalized,
    ):
        strong_match = True

    return (
        strong_match,
        related_match,
    )


# ============================================================
# NATIONALITY MATCHING
# ============================================================

def nationality_match(
    nationality_text: str,
) -> tuple[str, bool, bool]:

    text = normalize(
        nationality_text
    )

    if not text:
        return (
            "unknown",
            False,
            True,
        )

    open_patterns = [
        "open to all nationals",
        "all nationals",
        "open to international students",
        "international students",
        "all nationalities",
        "any nationality",
        "open to everyone",
    ]

    if any(
        pattern in text
        for pattern in open_patterns
    ):
        return (
            "open",
            False,
            False,
        )

    benin_patterns = [
        "benin",
        "beninese",
        "african nationals",
        "african students",
        "students from africa",
        "sub-saharan africa",
    ]

    if any(
        pattern in text
        for pattern in benin_patterns
    ):
        return (
            "eligible",
            False,
            False,
        )

    india_only_patterns = [
        "indian nationals only",
        "indian citizens only",
        "only indian nationals",
        "only indian citizens",
        "open to indian nationals only",
        "open to indian citizens only",
        "for indian nationals only",
        "for indian citizens only",
    ]

    if any(
        pattern in text
        for pattern in india_only_patterns
    ):
        return (
            "excluded",
            True,
            False,
        )

    restrictive_patterns = [
        "only citizens of",
        "citizens only",
        "nationals only",
        "residents only",
        "residents of",
        "citizens of",
    ]

    if any(
        pattern in text
        for pattern in restrictive_patterns
    ):

        if (
            "india" in text
            or "indian" in text
        ):
            return (
                "excluded",
                True,
                False,
            )

        return (
            "unknown",
            False,
            True,
        )

    # Merely mentioning Indian students is NOT enough
    # to declare the scholarship ineligible.
    if (
        "indian" in text
        or "india" in text
    ):
        return (
            "unknown",
            False,
            True,
        )

    return (
        "unknown",
        False,
        True,
    )


# ============================================================
# CGPA
# ============================================================

def extract_cgpa_requirements(
    text: str,
) -> list[str]:

    patterns = [

        r"\b(?:minimum|min|required|at least)"
        r"\s*(?:cgpa|gpa)"
        r"\s*(?:of|:)?\s*"
        r"\d+(?:\.\d+)?"
        r"(?:\s*(?:/|out of)\s*"
        r"\d+(?:\.\d+)?)?",

        r"\bcgpa"
        r"\s*(?:of|:)?\s*"
        r"\d+(?:\.\d+)?"
        r"(?:\s*(?:/|out of)\s*"
        r"\d+(?:\.\d+)?)?",

        r"\bgpa"
        r"\s*(?:of|:)?\s*"
        r"\d+(?:\.\d+)?"
        r"(?:\s*(?:/|out of)\s*"
        r"\d+(?:\.\d+)?)?",

        r"\bminimum\s+"
        r"\d+(?:\.\d+)?\s*%",

        r"\b\d+(?:\.\d+)?\s*%"
        r"\s*(?:or above|minimum|required)",
    ]

    results: list[str] = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:

            match = clean_text(match)

            if (
                match
                and match not in results
            ):
                results.append(match)

    return results[:10]


def parse_cgpa_requirement(
    requirement: str,
) -> tuple[float | None, float | None]:

    text = normalize(
        requirement
    )

    match = re.search(
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:/|out of)"
        r"\s*(\d+(?:\.\d+)?)",
        text,
    )

    if match:

        return (
            float(match.group(1)),
            float(match.group(2)),
        )

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*%",
        text,
    )

    if match:

        return (
            float(match.group(1)),
            100.0,
        )

    match = re.search(
        r"(?:cgpa|gpa)"
        r"\s*(?:of|:)?\s*"
        r"(\d+(?:\.\d+)?)",
        text,
    )

    if match:

        value = float(
            match.group(1)
        )

        if value <= 4:
            return (
                value,
                4.0,
            )

        if value <= 10:
            return (
                value,
                10.0,
            )

    return (
        None,
        None,
    )


def cgpa_eligibility(
    requirements: list[str],
) -> tuple[str, bool, list[str]]:

    if not requirements:

        return (
            "unknown",
            False,
            [
                "No clear CGPA/GPA requirement was found."
            ],
        )

    applicant_cgpa = STUDENT_PROFILE["cgpa"]
    applicant_scale = STUDENT_PROFILE[
        "cgpa_scale"
    ]

    reasons: list[str] = []

    for requirement in requirements:

        required, scale = (
            parse_cgpa_requirement(
                requirement
            )
        )

        if (
            required is None
            or scale is None
        ):
            continue

        applicant_normalized = (
            applicant_cgpa
            / applicant_scale
        )

        required_normalized = (
            required
            / scale
        )

        if (
            applicant_normalized
            >= required_normalized
        ):

            reasons.append(
                f"Your CGPA "
                f"{applicant_cgpa}/"
                f"{applicant_scale} "
                f"meets the detected "
                f"requirement "
                f"{requirement}."
            )

            return (
                "eligible",
                False,
                reasons,
            )

        reasons.append(
            f"Your CGPA "
            f"{applicant_cgpa}/"
            f"{applicant_scale} "
            f"is below the detected "
            f"requirement "
            f"{requirement}."
        )

        return (
            "excluded",
            True,
            reasons,
        )

    return (
        "unknown",
        False,
        [
            "A CGPA requirement was found "
            "but could not be reliably interpreted."
        ],
    )


# ============================================================
# AGE LIMIT
# ============================================================

def extract_age_limit(
    text: str,
) -> int | None:

    patterns = [
        r"under\s+(\d{2})\s+years?",
        r"below\s+(\d{2})\s+years?",
        r"less\s+than\s+(\d{2})\s+years?",
        r"maximum\s+age\s*(?:of|:)?\s*(\d{2})",
        r"age\s*(?:limit|maximum)"
        r"\s*(?:of|:)?\s*(\d{2})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return int(
                match.group(1)
            )

    return None


# ============================================================
# DESTINATION
# ============================================================

def detect_destination(
    destination_text: str,
    full_text: str,
) -> str:

    text = clean_text(
        destination_text
    )

    if not text:
        text = clean_text(
            full_text
        )

    countries = STUDENT_PROFILE[
        "preferred_destinations"
    ]

    found: list[str] = []

    normalized_text = normalize(
        text
    )

    for country in countries:

        if normalize(country) in normalized_text:
            found.append(country)

    if found:
        return ", ".join(
            unique_list(found)
        )

    location_patterns = [
        "worldwide",
        "any country",
        "all countries",
        "international",
        "universities across the world",
    ]

    for pattern in location_patterns:

        if pattern in normalized_text:
            return text[:500]

    return (
        text[:500]
        if text
        else "Unknown"
    )


# ============================================================
# MATCHING ENGINE
# ============================================================

def build_match(
    title: str,
    degree_text: str,
    field_text: str,
    nationality_text: str,
    destination_text: str,
    full_text: str,
    deadlines: list[str],
    cgpa_requirements: list[str],
) -> dict[str, Any]:

    score = 0

    reasons: list[str] = []
    warnings: list[str] = []

    # --------------------------------------------------------
    # DEGREE
    # --------------------------------------------------------

    (
        master_found,
        conflicting_degree,
    ) = degree_matches_master(
        degree_text
    )

    if master_found:

        score += 30

        reasons.append(
            "The scholarship explicitly "
            "accepts Master's-level study."
        )

    elif conflicting_degree:

        score -= 40

        warnings.append(
            "The detected degree level "
            "appears to conflict with "
            "your Master's target."
        )

    else:

        warnings.append(
            "The scholarship's degree level "
            "could not be clearly confirmed."
        )

    # --------------------------------------------------------
    # FIELD
    # --------------------------------------------------------

    field_search_text = " ".join(
        [
            title,
            field_text,
        ]
    )

    (
        strong_field,
        related_field,
    ) = field_matches(
        field_search_text
    )

    if strong_field:

        score += 30

        reasons.append(
            "The scholarship is directly "
            "related to Computer Science / IT."
        )

    elif related_field:

        score += 18

        reasons.append(
            "The scholarship is related "
            "to a technical field relevant "
            "to Computer Science / IT."
        )

    else:

        score -= 25

        warnings.append(
            "No clear Computer Science / "
            "IT field match was detected."
        )

    # --------------------------------------------------------
    # NATIONALITY
    # --------------------------------------------------------

    (
        nationality_status,
        nationality_excluded,
        nationality_manual,
    ) = nationality_match(
        nationality_text
    )

    if nationality_status == "open":

        score += 20

        reasons.append(
            "The scholarship is open to "
            "all nationals/international students."
        )

    elif nationality_status == "eligible":

        score += 20

        reasons.append(
            "The nationality information "
            "explicitly includes your "
            "eligibility group."
        )

    elif nationality_excluded:

        score -= 60

        warnings.append(
            "The detected nationality "
            "restriction appears to exclude "
            "a Benin applicant."
        )

    elif nationality_manual:

        warnings.append(
            "Nationality eligibility "
            "needs manual confirmation."
        )

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    destination_normalized = normalize(
        destination_text
    )

    preferred_match = False

    for country in STUDENT_PROFILE[
        "preferred_destinations"
    ]:

        if normalize(country) in (
            destination_normalized
        ):
            preferred_match = True
            break

    if preferred_match:

        score += 10

        reasons.append(
            "The study destination matches "
            "one of your preferred countries."
        )

    elif destination_text:

        warnings.append(
            "Study destination detected as: "
            f"{destination_text[:300]}"
        )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    (
        cgpa_status,
        cgpa_excluded,
        cgpa_reasons,
    ) = cgpa_eligibility(
        cgpa_requirements
    )

    if cgpa_status == "eligible":

        score += 10

        reasons.extend(
            cgpa_reasons
        )

    elif cgpa_excluded:

        score -= 35

        warnings.extend(
            cgpa_reasons
        )

    else:

        warnings.extend(
            cgpa_reasons
        )

    # --------------------------------------------------------
    # AGE
    # --------------------------------------------------------

    age_limit = extract_age_limit(
        full_text
    )

    if age_limit is not None:

        applicant_age = calculate_age(
            STUDENT_PROFILE[
                "date_of_birth"
            ]
        )

        if applicant_age <= age_limit:

            score += 5

            reasons.append(
                f"Your age "
                f"({applicant_age}) is "
                f"within the detected "
                f"age limit of "
                f"{age_limit}."
            )

        else:

            score -= 30

            warnings.append(
                f"Your age "
                f"({applicant_age}) appears "
                f"to exceed the detected "
                f"age limit of "
                f"{age_limit}."
            )

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    normalized_full_text = normalize(
        full_text
    )

    if any(
        keyword in normalized_full_text
        for keyword in FUNDING_KEYWORDS
    ):

        score += 5

        reasons.append(
            "The page contains a "
            "scholarship/funding signal."
        )

    # --------------------------------------------------------
    # DEADLINE
    # --------------------------------------------------------

    if deadlines:

        if deadline_is_expired(
            deadlines
        ):

            score -= 20

            warnings.append(
                "The detected deadline "
                "appears to have expired."
            )

        else:

            reasons.append(
                "Detected deadline: "
                f"{deadlines[0]}"
            )

    else:

        warnings.append(
            "No clear deadline was detected."
        )

    # --------------------------------------------------------
    # NORMALIZE
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

    if nationality_excluded:

        status = "likely_not_eligible"

    elif cgpa_excluded:

        status = "likely_not_eligible"

    elif (
        conflicting_degree
        and not master_found
    ):

        status = "likely_not_eligible"

    elif score >= 75:

        status = "strong_match"

    elif score >= 55:

        status = "good_match"

    elif score >= 35:

        status = "possible_match"

    elif score >= 25:

        status = "needs_manual_check"

    else:

        status = "likely_not_eligible"

    return {
        "match_score": score,
        "match_status": status,
        "reasons": unique_list(
            reasons
        ),
        "warnings": unique_list(
            warnings
        ),
    }


# ============================================================
# LISTING PAGE
# ============================================================

async def process_listing_page(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    Actor.log.info(
        f"Scanning scholarship listing page: {url}"
    )

    found_urls: list[str] = []

    # --------------------------------------------------------
    # FIND INDIVIDUAL SCHOLARSHIP LINKS
    # --------------------------------------------------------

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

        absolute_url = urljoin(
            url,
            href,
        )

        parsed = urlparse(
            absolute_url
        )

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

        if not is_scholarship_detail_url(
            clean_url
        ):
            continue

        if clean_url not in found_urls:

            found_urls.append(
                clean_url
            )

        if (
            len(found_urls)
            >= MAX_SCHOLARSHIP_LINKS_PER_PAGE
        ):
            break

    Actor.log.info(
        f"Found {len(found_urls)} "
        "individual scholarship links."
    )

    # --------------------------------------------------------
    # IMPORTANT FIX
    #
    # Crawlee 1.10.3 in your Actor expects
    # URL strings here, not dictionaries.
    # --------------------------------------------------------

    if found_urls:

        await context.add_requests(
            found_urls
        )

        Actor.log.info(
            f"Queued {len(found_urls)} "
            "individual scholarship pages."
        )

    else:

        Actor.log.warning(
            "No individual scholarship "
            "links were found."
        )


# ============================================================
# INDIVIDUAL SCHOLARSHIP PAGE
# ============================================================

async def process_scholarship_page(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    Actor.log.info(
        f"Analyzing individual scholarship: {url}"
    )

    # --------------------------------------------------------
    # BASIC PAGE INFORMATION
    # --------------------------------------------------------

    title = get_title(
        context
    )

    h1s, h2s, h3s = get_headings(
        context
    )

    multiline_text = get_multiline_text(
        context
    )

    full_text = get_page_text(
        context
    )

    # --------------------------------------------------------
    # ACTUAL SCHOLARSHIP FIELDS
    # --------------------------------------------------------

    degree_requirements = (
        extract_degree_requirements(
            multiline_text
        )
    )

    field_requirements = (
        extract_field_requirements(
            multiline_text
        )
    )

    nationality_requirements = (
        extract_nationality_requirements(
            multiline_text
        )
    )

    destination_text = extract_destination(
        multiline_text
    )

    deadlines = extract_deadlines(
        multiline_text
    )

    cgpa_requirements = (
        extract_cgpa_requirements(
            full_text
        )
    )

    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

    match = build_match(
        title=title,
        degree_text=degree_requirements,
        field_text=field_requirements,
        nationality_text=nationality_requirements,
        destination_text=destination_text,
        full_text=full_text,
        deadlines=deadlines,
        cgpa_requirements=cgpa_requirements,
    )

    # --------------------------------------------------------
    # SAVE RESULT
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
            "raw": degree_requirements,
            "target": STUDENT_PROFILE[
                "degree"
            ],
        },

        "field_requirements": {
            "raw": field_requirements,
            "target": STUDENT_PROFILE[
                "field"
            ],
        },

        "nationality_requirements": {
            "raw": nationality_requirements,
            "student_nationality": (
                STUDENT_PROFILE[
                    "nationality"
                ]
            ),
        },

        "cgpa_requirements": (
            cgpa_requirements
        ),

        "destination": (
            destination_text
        ),

        "deadlines": deadlines,

        "deadline_status": (
            "expired"
            if deadline_is_expired(
                deadlines
            )
            else "active_or_unknown"
        ),

        "h1s": h1s,

        "h2s": h2s,

        "h3s": h3s,
    }

    await context.push_data(
        record
    )

    Actor.log.info(
        f"RESULT: {title} | "
        f"score={match['match_score']} | "
        f"status={match['match_status']}"
    )


# ============================================================
# MAIN ROUTER
# ============================================================

@router.default_handler
async def default_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    # Individual scholarship page
    if is_scholarship_detail_url(
        url
    ):

        await process_scholarship_page(
            context
        )

        return

    # Category/listing page
    if is_listing_page(
        url
    ):

        await process_listing_page(
            context
        )

        return

    # Anything else
    Actor.log.info(
        f"Skipping non-scholarship page: {url}"
    )
