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


MAX_SCHOLARSHIP_LINKS_PER_PAGE = 40

SCHOLARSHIP_URL_RE = re.compile(
    r"^/scholarship/[^/?#]+/?$",
    re.IGNORECASE,
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize(value: str | None) -> str:
    return clean_text(value).lower()


def unique_list(values: list[str]) -> list[str]:
    seen = set()
    result = []

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def page_text(context: BeautifulSoupCrawlingContext) -> str:
    soup = context.soup

    for tag in soup.find_all(
        ["script", "style", "noscript", "svg", "iframe"]
    ):
        tag.decompose()

    return clean_text(
        soup.get_text(" ", strip=True)
    )


def page_lines(context: BeautifulSoupCrawlingContext) -> list[str]:
    soup = context.soup

    for tag in soup.find_all(
        ["script", "style", "noscript", "svg", "iframe"]
    ):
        tag.decompose()

    return [
        clean_text(x)
        for x in soup.get_text("\n").splitlines()
        if clean_text(x)
    ]


def get_title(context: BeautifulSoupCrawlingContext) -> str:
    tag = context.soup.find("title")

    if tag:
        value = clean_text(tag.get_text())
        if value:
            return value

    h1 = context.soup.find("h1")

    if h1:
        value = clean_text(h1.get_text())
        if value:
            return value

    return "Unknown scholarship"


def get_headings(
    context: BeautifulSoupCrawlingContext,
) -> tuple[list[str], list[str], list[str]]:

    h1s = unique_list([
        clean_text(x.get_text())
        for x in context.soup.find_all("h1")
    ])

    h2s = unique_list([
        clean_text(x.get_text())
        for x in context.soup.find_all("h2")
    ])

    h3s = unique_list([
        clean_text(x.get_text())
        for x in context.soup.find_all("h3")
    ])

    return h1s, h2s, h3s


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
        SCHOLARSHIP_URL_RE.fullmatch(
            parsed.path.lower()
        )
    )


def is_listing_url(url: str) -> bool:
    return not is_scholarship_url(url)


# ============================================================
# FIELD EXTRACTION
# ============================================================

FIELD_LABELS = [
    "Eligible Degrees",
    "Eligible Degree",
    "Eligible Courses",
    "Eligible Course",
    "Eligible Nationalities",
    "Eligible Nationality",
    "Can Be Taken At",
    "Study At",
    "Funding Type",
    "Deadline",
    "Provider",
    "Last Verified On",
    "Overview",
    "Scholarship Details",
]


def extract_labeled_section(
    lines: list[str],
    labels: list[str],
) -> str:

    normalized_lines = [
        normalize(line)
        for line in lines
    ]

    normalized_labels = [
        normalize(label)
        for label in labels
    ]

    for i, line in enumerate(normalized_lines):

        matched = None

        for label in normalized_labels:

            if line == label or line.startswith(label + ":"):
                matched = label
                break

        if matched is None:
            continue

        values = []

        # Collect following lines until another known field label.
        for next_line in lines[i + 1:i + 12]:

            normalized_next = normalize(
                next_line
            )

            if normalized_next in normalized_labels:
                break

            if any(
                normalized_next.startswith(
                    other + ":"
                )
                for other in normalized_labels
            ):
                break

            values.append(next_line)

        result = clean_text(
            " ".join(values)
        )

        if result:
            return result

    return ""


def extract_degree(
    lines: list[str],
    title: str,
    headings: list[str],
) -> str:

    result = extract_labeled_section(
        lines,
        [
            "Eligible Degrees",
            "Eligible Degree",
        ],
    )

    if result:
        return result

    # Fallback to title/headings.
    fallback = " ".join(
        [title, *headings]
    )

    return clean_text(fallback)


def extract_field(
    lines: list[str],
    title: str,
    headings: list[str],
) -> str:

    result = extract_labeled_section(
        lines,
        [
            "Eligible Courses",
            "Eligible Course",
        ],
    )

    if result:
        return result

    return clean_text(
        " ".join(
            [title, *headings]
        )
    )


def extract_nationality(
    lines: list[str],
) -> str:

    return extract_labeled_section(
        lines,
        [
            "Eligible Nationalities",
            "Eligible Nationality",
        ],
    )


def extract_destination(
    lines: list[str],
) -> str:

    result = extract_labeled_section(
        lines,
        [
            "Can Be Taken At",
            "Study At",
        ],
    )

    return result


# ============================================================
# DEGREE MATCHING
# ============================================================

def has_master(text: str) -> bool:
    return bool(
        re.search(
            r"\bmaster(?:'s)?s?\b"
            r"|\bmsc\b"
            r"|\bm\.sc\b",
            normalize(text),
        )
    )


def has_phd(text: str) -> bool:
    return bool(
        re.search(
            r"\bph\.?d\b"
            r"|\bdoctorate\b",
            normalize(text),
        )
    )


def has_bachelor(text: str) -> bool:
    return bool(
        re.search(
            r"\bbachelor(?:'s)?s?\b"
            r"|\bbsc\b"
            r"|\bb\.sc\b",
            normalize(text),
        )
    )


def degree_match(
    degree_text: str,
    title: str,
) -> tuple[bool, bool]:

    degree = normalize(degree_text)
    title_normalized = normalize(title)

    # If title explicitly says PhD and not Master,
    # don't call it a Master's match.
    if has_phd(title_normalized) and not has_master(
        title_normalized
    ):
        return False, True

    if has_bachelor(title_normalized) and not has_master(
        title_normalized
    ):
        return False, True

    if has_master(degree):
        return True, False

    if has_master(title_normalized):
        return True, False

    if has_phd(degree) or has_bachelor(degree):
        return False, True

    return False, False


# ============================================================
# FIELD MATCHING
# ============================================================

def field_match(text: str) -> tuple[bool, bool]:

    text = normalize(text)

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

    strong_match = any(
        keyword in text
        for keyword in strong
    )

    related_match = any(
        keyword in text
        for keyword in related
    )

    # IMPORTANT:
    # IT must be a complete word.
    if re.search(r"\bit\b", text):
        strong_match = True

    return strong_match, related_match


# ============================================================
# NATIONALITY MATCHING
# ============================================================

def nationality_match(
    text: str,
) -> tuple[str, bool]:

    text = normalize(text)

    if not text:
        return "unknown", False

    open_patterns = [
        "open to all nationals",
        "all nationals",
        "all nationalities",
        "open to international students",
        "international students",
        "any nationality",
        "open to everyone",
    ]

    if any(
        x in text
        for x in open_patterns
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
        "for indian nationals only",
        "for indian citizens only",
    ]

    if any(
        x in text
        for x in india_only
    ):
        return "excluded", True

    if (
        "citizens only" in text
        or "nationals only" in text
        or "only citizens of" in text
    ):
        return "unknown", True

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

            match = clean_text(match)

            if match and match not in results:
                results.append(match)

    return results[:10]


def parse_cgpa(
    requirement: str,
) -> tuple[float | None, float | None]:

    text = normalize(
        requirement
    )

    match = re.search(
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:/|out of)\s*"
        r"(\d+(?:\.\d+)?)",
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
            return value, 4.0

        if value <= 10:
            return value, 10.0

    return None, None


def check_cgpa(
    requirements: list[str],
) -> tuple[str, bool, list[str]]:

    if not requirements:
        return (
            "unknown",
            False,
            ["No clear CGPA requirement detected."],
        )

    applicant = (
        STUDENT_PROFILE["cgpa"]
        / STUDENT_PROFILE["cgpa_scale"]
    )

    for requirement in requirements:

        required, scale = parse_cgpa(
            requirement
        )

        if required is None:
            continue

        required_normalized = (
            required / scale
        )

        if applicant >= required_normalized:

            return (
                "eligible",
                False,
                [
                    f"Your CGPA "
                    f"{STUDENT_PROFILE['cgpa']}/"
                    f"{STUDENT_PROFILE['cgpa_scale']} "
                    f"meets {requirement}."
                ],
            )

        return (
            "excluded",
            True,
            [
                f"Your CGPA "
                f"{STUDENT_PROFILE['cgpa']}/"
                f"{STUDENT_PROFILE['cgpa_scale']} "
                f"is below {requirement}."
            ],
        )

    return (
        "unknown",
        False,
        ["CGPA requirement could not be interpreted."],
    )


# ============================================================
# DESTINATION
# ============================================================

def find_destination(
    destination: str,
    full_text: str,
) -> str:

    text = normalize(
        destination or full_text
    )

    found = []

    for country in STUDENT_PROFILE[
        "preferred_destinations"
    ]:

        if normalize(country) in text:
            found.append(country)

    if found:
        return ", ".join(
            unique_list(found)
        )

    return clean_text(
        destination
    ) or "Unknown"


# ============================================================
# DEADLINES
# ============================================================

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)

DATE_RE = re.compile(
    rf"(?:"
    rf"(?:0?[1-9]|[12]\d|3[01])"
    rf"(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}}"
    rf"|"
    rf"(?:{MONTHS})\s+(?:0?[1-9]|[12]\d|3[01])"
    rf"(?:st|nd|rd|th)?[,]?\s+\d{{4}}"
    rf"|"
    rf"\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{4}}"
    rf")",
    re.IGNORECASE,
)


def extract_deadlines(
    text: str,
) -> list[str]:

    return unique_list(
        [
            clean_text(x)
            for x in DATE_RE.findall(text)
        ]
    )[:10]


def expired_deadline(
    deadlines: list[str],
) -> bool:

    formats = [
        "%d %B %Y",
        "%B %d %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ]

    parsed = []

    for raw in deadlines:

        cleaned = re.sub(
            r"(st|nd|rd|th)",
            "",
            raw,
            flags=re.IGNORECASE,
        )

        for fmt in formats:

            try:
                parsed.append(
                    datetime.strptime(
                        cleaned,
                        fmt,
                    )
                )
                break
            except ValueError:
                pass

    if not parsed:
        return False

    today = datetime.now().date()

    return all(
        x.date() < today
        for x in parsed
    )


# ============================================================
# AGE
# ============================================================

def get_age() -> int:

    dob = datetime.strptime(
        STUDENT_PROFILE["date_of_birth"],
        "%Y-%m-%d",
    ).date()

    today = datetime.now().date()

    age = (
        today.year
        - dob.year
    )

    if (
        today.month,
        today.day
    ) < (
        dob.month,
        dob.day
    ):
        age -= 1

    return age


def get_age_limit(
    text: str,
) -> int | None:

    patterns = [
        r"under\s+(\d{2})\s+years",
        r"below\s+(\d{2})\s+years",
        r"maximum age.*?(\d{2})",
        r"age limit.*?(\d{2})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return int(
                match.group(1)
            )

    return None


# ============================================================
# MATCHING
# ============================================================

def calculate_match(
    title: str,
    degree: str,
    field: str,
    nationality: str,
    destination: str,
    full_text: str,
    deadlines: list[str],
    cgpa_requirements: list[str],
) -> dict[str, Any]:

    score = 0
    reasons = []
    warnings = []

    # --------------------------------------------------------
    # DEGREE
    # --------------------------------------------------------

    master, conflicting = degree_match(
        degree,
        title,
    )

    if master:

        score += 30

        reasons.append(
            "Master's-level study detected."
        )

    elif conflicting:

        score -= 45

        warnings.append(
            "The scholarship appears to target "
            "a different degree level."
        )

    else:

        warnings.append(
            "Master's eligibility could not "
            "be confirmed."
        )

    # --------------------------------------------------------
    # FIELD
    # --------------------------------------------------------

    strong_field, related_field = field_match(
        f"{title} {field}"
    )

    if strong_field:

        score += 30

        reasons.append(
            "Computer Science / IT relevance detected."
        )

    elif related_field:

        score += 18

        reasons.append(
            "Related technical field detected."
        )

    else:

        score -= 25

        warnings.append(
            "Computer Science / IT relevance "
            "could not be confirmed."
        )

    # --------------------------------------------------------
    # NATIONALITY
    # --------------------------------------------------------

    nationality_status, nationality_restricted = (
        nationality_match(
            nationality
        )
    )

    if nationality_status == "eligible":

        score += 20

        reasons.append(
            "Nationality appears eligible."
        )

    elif nationality_restricted:

        score -= 50

        warnings.append(
            "Nationality eligibility needs "
            "careful manual confirmation."
        )

    else:

        warnings.append(
            "Nationality eligibility is unclear."
        )

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    destination_normalized = normalize(
        destination
    )

    preferred = any(
        normalize(country)
        in destination_normalized
        for country in STUDENT_PROFILE[
            "preferred_destinations"
        ]
    )

    if preferred:

        score += 10

        reasons.append(
            "Preferred destination detected."
        )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    cgpa_status, cgpa_bad, cgpa_reasons = (
        check_cgpa(
            cgpa_requirements
        )
    )

    if cgpa_status == "eligible":

        score += 10

        reasons.extend(
            cgpa_reasons
        )

    elif cgpa_bad:

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

    age_limit = get_age_limit(
        full_text
    )

    if age_limit:

        age = get_age()

        if age <= age_limit:

            score += 5

            reasons.append(
                f"Age {age} is within "
                f"the detected limit."
            )

        else:

            score -= 30

            warnings.append(
                f"Age {age} may exceed "
                f"the detected limit."
            )

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    funding_words = [
        "fully funded",
        "full funding",
        "partial funding",
        "tuition fee",
        "tuition fees",
        "stipend",
        "scholarship amount",
        "financial support",
        "grant",
        "fellowship",
    ]

    if any(
        word in normalize(full_text)
        for word in funding_words
    ):

        score += 5

        reasons.append(
            "Funding information detected."
        )

    # --------------------------------------------------------
    # DEADLINE
    # --------------------------------------------------------

    if deadlines:

        if expired_deadline(
            deadlines
        ):

            score -= 20

            warnings.append(
                "Detected deadline may have expired."
            )

        else:

            reasons.append(
                f"Deadline detected: {deadlines[0]}"
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

    if conflicting and not master:
        status = "likely_not_eligible"

    elif nationality_status == "excluded":
        status = "likely_not_eligible"

    elif cgpa_bad:
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
        "reasons": unique_list(reasons),
        "warnings": unique_list(warnings),
    }


# ============================================================
# LISTING PAGE
# ============================================================

async def process_listing_page(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    Actor.log.info(
        f"Scanning listing page: {url}"
    )

    scholarship_urls = []

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

        absolute = urljoin(
            url,
            href,
        )

        parsed = urlparse(
            absolute
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

        if not is_scholarship_url(
            clean_url
        ):
            continue

        if clean_url not in scholarship_urls:

            scholarship_urls.append(
                clean_url
            )

        if len(
            scholarship_urls
        ) >= MAX_SCHOLARSHIP_LINKS_PER_PAGE:
            break

    Actor.log.info(
        f"Found {len(scholarship_urls)} "
        "individual scholarship links."
    )

    # IMPORTANT:
    # Crawlee 1.10.3 expects strings here.
    if scholarship_urls:

        await context.add_requests(
            scholarship_urls
        )

        Actor.log.info(
            f"Queued {len(scholarship_urls)} "
            "individual scholarship pages."
        )


# ============================================================
# INDIVIDUAL SCHOLARSHIP PAGE
# ============================================================

async def process_scholarship_page(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = context.request.url

    Actor.log.info(
        f"Analyzing scholarship: {url}"
    )

    title = get_title(
        context
    )

    h1s, h2s, h3s = get_headings(
        context
    )

    lines = page_lines(
        context
    )

    full_text = page_text(
        context
    )

    all_headings = [
        *h1s,
        *h2s,
        *h3s,
    ]

    # --------------------------------------------------------
    # EXTRACT
    # --------------------------------------------------------

    degree_requirements = extract_degree(
        lines,
        title,
        all_headings,
    )

    field_requirements = extract_field(
        lines,
        title,
        all_headings,
    )

    nationality_requirements = extract_nationality(
        lines
    )

    destination = extract_destination(
        lines
    )

    deadlines = extract_deadlines(
        full_text
    )

    cgpa_requirements = extract_cgpa(
        full_text
    )

    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

    match = calculate_match(
        title=title,
        degree=degree_requirements,
        field=field_requirements,
        nationality=nationality_requirements,
        destination=destination,
        full_text=full_text,
        deadlines=deadlines,
        cgpa_requirements=cgpa_requirements,
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
            "raw": degree_requirements,
            "target": "Master",
        },

        "field_requirements": {
            "raw": field_requirements,
            "target": "Computer Science",
        },

        "nationality_requirements": {
            "raw": nationality_requirements,
            "student_nationality": "Benin",
        },

        "cgpa_requirements": (
            cgpa_requirements
        ),

        "destination": destination,

        "deadlines": deadlines,

        "deadline_status": (
            "expired"
            if expired_deadline(
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
        f"RESULT | "
        f"{title} | "
        f"score={match['match_score']} | "
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

    if is_scholarship_url(
        url
    ):

        await process_scholarship_page(
            context
        )

        return

    await process_listing_page(
        context
    )
