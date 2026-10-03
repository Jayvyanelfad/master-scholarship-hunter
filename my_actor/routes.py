"""Crawler routes for Master Scholarship Hunter."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawlingContext
from crawlee.router import Router

from .profile_rules import STUDENT_PROFILE, strict_match


router = Router[BeautifulSoupCrawlingContext]()


# ============================================================
# CONFIGURATION
# ============================================================

WMS_DOMAINS = {
    "www.wemakescholars.com",
    "wemakescholars.com",
    "zeta.wemakescholars.com",
}

SCHOLARSHIP_PATH_MARKERS = (
    "/scholarship/",
    "/scholarships/",
)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            output.append(value)

    return output


def page_text(context: BeautifulSoupCrawlingContext) -> str:
    return clean_text(
        context.soup.get_text(
            " ",
            strip=True,
        )
    )


# ============================================================
# URL HELPERS
# ============================================================

def is_wms(url: str) -> bool:
    try:
        hostname = (
            urlparse(url).hostname
            or ""
        ).lower()

        return hostname in WMS_DOMAINS

    except Exception:
        return False


def is_scholarship_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme not in (
        "http",
        "https",
    ):
        return False

    if not is_wms(url):
        return False

    path = parsed.path.lower()

    return any(
        marker in path
        for marker in SCHOLARSHIP_PATH_MARKERS
    )


# ============================================================
# LABEL EXTRACTION
# ============================================================

def extract_after_label(
    text: str,
    labels: list[str],
) -> str:
    """
    Extract a short value appearing after one of
    the supplied labels.
    """

    for label in labels:

        pattern = re.compile(
            rf"{re.escape(label)}"
            rf"\s*[:\-]?\s*"
            rf"(.{{1,500}}?)"
            rf"(?=\s{{2,}}|"
            rf"Eligible|"
            rf"Deadline|"
            rf"Application|"
            rf"Funding|"
            rf"Scholarship|"
            rf"$)",
            re.IGNORECASE,
        )

        match = pattern.search(text)

        if match:

            value = clean_text(
                match.group(1)
            )

            if value:
                return value

    return ""


# ============================================================
# DESTINATION
# ============================================================

COUNTRY_NAMES = {
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
    "Japan",
    "Singapore",
}


def extract_destination(
    title: str,
    text: str,
) -> str:

    combined = " ".join(
        [
            title,
            text[:12000],
        ]
    )

    matches: list[str] = []

    for country in COUNTRY_NAMES:

        if re.search(
            rf"\b{re.escape(country)}\b",
            combined,
            re.IGNORECASE,
        ):
            matches.append(country)

    matches = unique(matches)

    # Prefer the actual target country list.
    preferred = [
        x
        for x in matches
        if x.lower()
        in {
            y.lower()
            for y in STUDENT_PROFILE[
                "preferred_destinations"
            ]
        }
    ]

    if preferred:
        return preferred[0]

    if matches:
        return matches[0]

    return ""


# ============================================================
# DEGREE
# ============================================================

def extract_degree(
    title: str,
    text: str,
) -> str:

    combined = " ".join(
        [
            title,
            text[:10000],
        ]
    )

    degrees: list[str] = []

    if re.search(
        r"\bmaster(?:'s|s)?\b"
        r"|\bmsc\b"
        r"|\bm\.sc\b",
        combined,
        re.IGNORECASE,
    ):
        degrees.append("Master")

    if re.search(
        r"\bph\.?\s*d\.?\b"
        r"|\bdoctorate\b"
        r"|\bdoctoral\b",
        combined,
        re.IGNORECASE,
    ):
        degrees.append("PhD")

    if re.search(
        r"\bbachelor(?:'s|s)?\b"
        r"|\bbsc\b"
        r"|\bb\.sc\b",
        combined,
        re.IGNORECASE,
    ):
        degrees.append("Bachelor")

    return ", ".join(
        unique(degrees)
    )


# ============================================================
# FIELD
# ============================================================

def extract_field(
    title: str,
    text: str,
) -> str:

    combined = " ".join(
        [
            title,
            text[:12000],
        ]
    ).lower()

    terms = [
        "Computer Science",
        "Information Technology",
        "Information Systems",
        "Software Engineering",
        "Computer Engineering",
        "Artificial Intelligence",
        "Machine Learning",
        "Deep Learning",
        "Generative AI",
        "Agentic AI",
        "AI Engineering",
        "Intelligent Systems",
        "Natural Language Processing",
        "Computer Vision",
        "Robotics",
        "Autonomous Systems",
        "Data Science",
        "Data Engineering",
        "Big Data",
        "Cybersecurity",
        "Information Security",
        "Cloud Computing",
        "Distributed Systems",
    ]

    found = [
        term
        for term in terms
        if term.lower() in combined
    ]

    return ", ".join(
        unique(found)
    )


# ============================================================
# NATIONALITY
# ============================================================

def extract_nationality(
    text: str,
) -> str:

    lower = text.lower()

    if any(
        phrase in lower
        for phrase in (
            "open to all nationals",
            "open to all nationalities",
            "all nationals",
            "all nationalities",
            "any nationality",
            "open to international students",
            "open to all international students",
        )
    ):
        return "All international / all nationalities"

    if (
        "benin" in lower
        or "beninese" in lower
    ):
        return "Benin / Beninese"

    if any(
        phrase in lower
        for phrase in (
            "indian nationals only",
            "only indian nationals",
            "indian citizens only",
            "only indian citizens",
            "indian students only",
        )
    ):
        return "India only"

    return ""


# ============================================================
# FUNDING
# ============================================================

def extract_funding(
    title: str,
    text: str,
) -> str:

    combined = " ".join(
        [
            title,
            text[:15000],
        ]
    )

    funding_terms = [
        "fully funded",
        "full funding",
        "full scholarship",
        "fully-funded",
        "tuition fees",
        "full tuition",
        "living allowance",
        "living expenses",
        "monthly stipend",
        "maintenance allowance",
        "maintenance stipend",
        "travel allowance",
        "airfare",
        "accommodation",
        "bursary",
        "partial funding",
        "tuition waiver",
    ]

    found: list[str] = []

    for term in funding_terms:

        if term.lower() in combined.lower():
            found.append(term)

    return ", ".join(
        unique(found)
    )


# ============================================================
# DEADLINE
# ============================================================

def extract_deadline(
    text: str,
) -> str:

    patterns = [
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"(?:\s*,?\s*)"
        r"\d{4}\b",

        r"\b\d{1,2}\s+"
        r"(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"(?:\s*,?\s*)"
        r"\d{4}\b",

        r"\b(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+\d{1,2},?\s+\d{4}\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return clean_text(
                match.group(0)
            )

    return ""


# ============================================================
# CGPA
# ============================================================

def extract_cgpa(
    text: str,
) -> list[str]:

    patterns = [
        r"\b\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\b",
        r"\b\d+(?:\.\d+)?\s+out\s+of\s+\d+(?:\.\d+)?\b",
    ]

    values: list[str] = []

    for pattern in patterns:

        values.extend(
            re.findall(
                pattern,
                text,
                re.IGNORECASE,
            )
        )

    return unique(values)


# ============================================================
# ROUTE 1 — SCHOLARSHIP PAGE
# ============================================================

@router.handler("SCHOLARSHIP")
async def scholarship_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:

    response_url = str(
        context.request.url
    )

    soup = context.soup

    title = clean_text(
        soup.title.get_text(
            strip=True
        )
        if soup.title
        else ""
    )

    h1 = clean_text(
        soup.h1.get_text(
            strip=True
        )
        if soup.h1
        else ""
    )

    if h1:
        title = h1

    text = page_text(context)

    # --------------------------------------------------------
    # Extract scholarship information
    # --------------------------------------------------------

    destination = extract_destination(
        title,
        text,
    )

    degree = extract_degree(
        title,
        text,
    )

    field = extract_field(
        title,
        text,
    )

    nationality = extract_nationality(
        text,
    )

    funding = extract_funding(
        title,
        text,
    )

    deadline = extract_deadline(
        text,
    )

    cgpa_requirements = extract_cgpa(
        text,
    )

    # --------------------------------------------------------
    # Strict matching
    # --------------------------------------------------------

    result = strict_match(
        title=title,
        degree=degree,
        courses=field,
        nationality=nationality,
        destination=destination,
        deadline=deadline,
        cgpa_requirements=cgpa_requirements,
        funding=funding,
        page_text=text,
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    record = {
        "record_type": "scholarship",

        "title": title or "Unknown scholarship",

        "url": response_url,

        "source_domain": (
            urlparse(response_url)
            .hostname
            or ""
        ),

        "destination": destination,

        "degree_requirements": degree,

        "field_requirements": field,

        "nationality_requirements": nationality,

        "funding": funding,

        "cgpa_requirements": cgpa_requirements,

        "deadlines": deadline,

        "student_profile": STUDENT_PROFILE,

        "match_score": result[
            "match_score"
        ],

        "match_status": result[
            "match_status"
        ],

        "recommendation": result[
            "recommendation"
        ],

        "reasons": result[
            "reasons"
        ],

        "warnings": result[
            "warnings"
        ],

        "degree_match": result[
            "degree_match"
        ],

        "field_match": result[
            "field_match"
        ],

        "nationality_match": result[
            "nationality_match"
        ],

        "funding_status": result[
            "funding_status"
        ],

        "destination_match": result[
            "destination_match"
        ],

        "application_from_abroad": result[
            "application_from_abroad"
        ],

        "cgpa_match": result[
            "cgpa_match"
        ],

        "deadline_state": result[
            "deadline_state"
        ],

        "profile_version": result[
            "profile_version"
        ],

        "profile_rule": result[
            "profile_rule"
        ],
    }

    await context.push_data(
        record
    )

    Actor.log.info(
        "Scholarship processed: "
        f"{title[:100]} | "
        f"{result['match_status']} | "
        f"{result['match_score']}"
    )


# ============================================================
# ROUTE 2 — START/CATEGORY PAGE
# ============================================================

@router.handler("START")
async def start_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:

    current_url = str(
        context.request.url
    )

    Actor.log.info(
        f"Scanning scholarship listing: "
        f"{current_url}"
    )

    found = 0

    for link in context.soup.select(
        "a[href]"
    ):

        href = link.get(
            "href"
        )

        if not href:
            continue

        absolute_url = urljoin(
            current_url,
            href,
        )

        if not is_scholarship_url(
            absolute_url
        ):
            continue

        # Crawlee expects URL strings here.
        await context.add_requests(
            [absolute_url]
        )

        found += 1

    Actor.log.info(
        f"Found {found} individual scholarship URL(s)."
    )


# ============================================================
# DEFAULT ROUTE
# ============================================================

@router.default_handler
async def default_handler(
    context: BeautifulSoupCrawlingContext,
) -> None:

    url = str(
        context.request.url
    )

    if is_scholarship_url(url):

        await scholarship_handler(
            context
        )

    else:

        await start_handler(
            context
        )