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
# STUDENT PROFILE
# ============================================================

from .profile_rules import STUDENT_PROFILE, strict_match

# ============================================================
# CONFIGURATION
# ============================================================

WMS_DOMAINS = {
    "www.wemakescholars.com",
    "wemakescholars.com",
    "zeta.wemakescholars.com",
}

MAX_SCHOLARSHIP_LINKS = 100


# ============================================================
# COUNTRY NORMALIZATION
# ============================================================

COUNTRY_ALIASES = {
    "usa": "United States",
    "u.s.a": "United States",
    "u.s.": "United States",
    "us": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "america": "United States",

    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",

    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",

    "south korea": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",

    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",

    "russia": "Russia",
    "russian federation": "Russia",

    "iran": "Iran",
    "islamic republic of iran": "Iran",

    "tanzania": "Tanzania",
    "united republic of tanzania": "Tanzania",

    "congo": "Republic of the Congo",
    "democratic republic of the congo": "Democratic Republic of the Congo",
    "drc": "Democratic Republic of the Congo",

    "ivory coast": "Côte d'Ivoire",
    "cote d'ivoire": "Côte d'Ivoire",

    "benin": "Benin",
    "beninese": "Benin",

    "netherlands": "Netherlands",
    "holland": "Netherlands",

    "germany": "Germany",
    "france": "France",
    "belgium": "Belgium",
    "finland": "Finland",
    "sweden": "Sweden",
    "norway": "Norway",
    "denmark": "Denmark",
    "ireland": "Ireland",
    "canada": "Canada",
    "australia": "Australia",
    "austria": "Austria",
    "switzerland": "Switzerland",
    "luxembourg": "Luxembourg",

    "spain": "Spain",
    "italy": "Italy",
    "portugal": "Portugal",
    "poland": "Poland",
    "czech": "Czech Republic",
    "hungary": "Hungary",
    "greece": "Greece",
    "romania": "Romania",
    "bulgaria": "Bulgaria",
    "croatia": "Croatia",
    "slovenia": "Slovenia",
    "slovakia": "Slovakia",
    "estonia": "Estonia",
    "latvia": "Latvia",
    "lithuania": "Lithuania",
    "iceland": "Iceland",

    "japan": "Japan",
    "china": "China",
    "india": "India",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "indonesia": "Indonesia",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
    "philippines": "Philippines",

    "new zealand": "New Zealand",
    "south africa": "South Africa",
    "nigeria": "Nigeria",
    "ghana": "Ghana",
    "kenya": "Kenya",
    "rwanda": "Rwanda",
    "uganda": "Uganda",
    "senegal": "Senegal",
    "morocco": "Morocco",
    "egypt": "Egypt",
}


# ============================================================
# UNIVERSITY / INSTITUTION LOCATION KNOWLEDGE
#
# This handles cases where WMS gives only:
# "IE University"
# instead of:
# "IE University, Spain"
#
# The raw destination is ALWAYS preserved.
# ============================================================

INSTITUTION_COUNTRIES = {
    # Spain
    "ie university": "Spain",
    "universidad ie": "Spain",
    "ie school of human sciences": "Spain",

    # Netherlands
    "ihe delft institute for water education": "Netherlands",
    "delft university of technology": "Netherlands",
    "tu delft": "Netherlands",
    "erasmus university rotterdam": "Netherlands",
    "university of amsterdam": "Netherlands",
    "vrije universiteit amsterdam": "Netherlands",
    "utrecht university": "Netherlands",
    "leiden university": "Netherlands",
    "university of groningen": "Netherlands",
    "maastricht university": "Netherlands",
    "radboud university": "Netherlands",
    "eindhoven university of technology": "Netherlands",
    "tilburg university": "Netherlands",

    # Germany
    "technical university of munich": "Germany",
    "tum": "Germany",
    "ludwig maximilian university of munich": "Germany",
    "heidelberg university": "Germany",
    "rwth aachen university": "Germany",
    "freiburg university": "Germany",
    "university of bonn": "Germany",
    "university of hamburg": "Germany",
    "free university of berlin": "Germany",
    "humboldt university of berlin": "Germany",
    "charité": "Germany",
    "charite": "Germany",

    # France
    "sorbonne university": "France",
    "université paris cité": "France",
    "universite paris cite": "France",
    "paris sciences et lettres": "France",
    "psl university": "France",
    "école polytechnique": "France",
    "ecole polytechnique": "France",
    "sciences po": "France",
    "université paris-saclay": "France",
    "universite paris saclay": "France",

    # Belgium
    "ku leuven": "Belgium",
    "katholieke universiteit leuven": "Belgium",
    "ghent university": "Belgium",
    "université libre de bruxelles": "Belgium",
    "universite libre de bruxelles": "Belgium",
    "vrije universiteit brussel": "Belgium",
    "university of antwerp": "Belgium",

    # Finland
    "aalto university": "Finland",
    "university of helsinki": "Finland",
    "university of turku": "Finland",
    "university of tampere": "Finland",
    "university of oulu": "Finland",
    "lut university": "Finland",
    "university of jyväskylä": "Finland",
    "university of jyvaskyla": "Finland",

    # Sweden
    "lund university": "Sweden",
    "uppsala university": "Sweden",
    "kth royal institute of technology": "Sweden",
    "kth": "Sweden",
    "chalmers university of technology": "Sweden",
    "stockholm university": "Sweden",
    "linköping university": "Sweden",
    "linkoping university": "Sweden",
    "umeå university": "Sweden",
    "umea university": "Sweden",

    # Norway
    "university of oslo": "Norway",
    "university of bergen": "Norway",
    "norwegian university of science and technology": "Norway",
    "ntnu": "Norway",
    "university of tromsø": "Norway",
    "university of tromso": "Norway",

    # Denmark
    "university of copenhagen": "Denmark",
    "technical university of denmark": "Denmark",
    "dtU": "Denmark",
    "aarhus university": "Denmark",
    "aalborg university": "Denmark",
    "copenhagen business school": "Denmark",

    # Ireland
    "trinity college dublin": "Ireland",
    "university college dublin": "Ireland",
    "university college cork": "Ireland",
    "university of galway": "Ireland",
    "dublin city university": "Ireland",
    "maynooth university": "Ireland",

    # Canada
    "university of toronto": "Canada",
    "university of british columbia": "Canada",
    "ubc": "Canada",
    "mcgill university": "Canada",
    "university of alberta": "Canada",
    "university of waterloo": "Canada",
    "mcMaster university": "Canada",
    "mcmaster university": "Canada",
    "university of ottawa": "Canada",
    "university of montreal": "Canada",
    "university of manitoba": "Canada",
    "university of calgary": "Canada",
    "university of saskatchewan": "Canada",
    "university of victoria": "Canada",
    "university of prince edward island": "Canada",

    # Australia
    "university of melbourne": "Australia",
    "monash university": "Australia",
    "university of sydney": "Australia",
    "university of queensland": "Australia",
    "unsw": "Australia",
    "university of new south wales": "Australia",
    "australian national university": "Australia",
    "anu": "Australia",
    "university of western australia": "Australia",
    "university of adelaide": "Australia",
    "deakin university": "Australia",
    "rmit university": "Australia",
    "queensland university of technology": "Australia",
    "cquniversity": "Australia",
    "cq university": "Australia",

    # Austria
    "university of vienna": "Austria",
    "vienna university of technology": "Austria",
    "tu wien": "Austria",
    "university of graz": "Austria",
    "university of innsbruck": "Austria",

    # Switzerland
    "eth zurich": "Switzerland",
    "eth zürich": "Switzerland",
    "epfl": "Switzerland",
    "university of zurich": "Switzerland",
    "university of zürich": "Switzerland",
    "university of geneva": "Switzerland",
    "university of bern": "Switzerland",

    # Luxembourg
    "university of luxembourg": "Luxembourg",

    # United Kingdom
    "university of oxford": "United Kingdom",
    "oxford university": "United Kingdom",
    "university of cambridge": "United Kingdom",
    "imperial college london": "United Kingdom",
    "university college london": "United Kingdom",
    "ucl": "United Kingdom",
    "king's college london": "United Kingdom",
    "kings college london": "United Kingdom",
    "university of edinburgh": "United Kingdom",
    "university of glasgow": "United Kingdom",
    "university of manchester": "United Kingdom",
    "university of bristol": "United Kingdom",
    "university of birmingham": "United Kingdom",
    "university of leeds": "United Kingdom",
    "university of sheffield": "United Kingdom",
    "university of nottingham": "United Kingdom",
    "university of southampton": "United Kingdom",
    "heriot-watt university": "United Kingdom",
    "heriot-watt university, edinburgh": "United Kingdom",

    # United States
    "harvard university": "United States",
    "stanford university": "United States",
    "massachusetts institute of technology": "United States",
    "mit": "United States",
    "yale university": "United States",
    "princeton university": "United States",
    "columbia university": "United States",
    "cornell university": "United States",
    "duke university": "United States",
    "vanderbilt university": "United States",
    "university of chicago": "United States",
    "university of california": "United States",
    "california state university": "United States",
    "california state university, sacramento": "United States",
    "sacramento state": "United States",
    "full sail university": "United States",
    "george mason university": "United States",
    "washington state university": "United States",
}


# ============================================================
# HELPERS
# ============================================================

def clean(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def normalize(value: str | None) -> str:
    return clean(value).lower()


def unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        value = clean(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            output.append(value)

    return output


def get_title(context: BeautifulSoupCrawlingContext) -> str:
    soup = context.soup

    title = soup.find("title")

    if title:
        value = clean(title.get_text(" ", strip=True))

        if value:
            return value

    h1 = soup.find("h1")

    if h1:
        value = clean(h1.get_text(" ", strip=True))

        if value:
            return value

    return "Unknown scholarship"


def get_headings(
    context: BeautifulSoupCrawlingContext,
) -> tuple[list[str], list[str], list[str]]:

    soup = context.soup

    h1s = unique(
        [
            clean(node.get_text(" ", strip=True))
            for node in soup.find_all("h1")
        ]
    )

    h2s = unique(
        [
            clean(node.get_text(" ", strip=True))
            for node in soup.find_all("h2")
        ]
    )

    h3s = unique(
        [
            clean(node.get_text(" ", strip=True))
            for node in soup.find_all("h3")
        ]
    )

    return h1s, h2s, h3s


def get_page_text(
    context: BeautifulSoupCrawlingContext,
) -> str:

    soup = context.soup

    # Do not mutate the original page unnecessarily.
    soup_copy = soup

    for tag in soup_copy.find_all(
        ["script", "style", "noscript", "svg", "iframe"]
    ):
        tag.decompose()

    return clean(
        soup_copy.get_text(" ", strip=True)
    )


def is_scholarship_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.netloc.lower() not in WMS_DOMAINS:
        return False

    return bool(
        re.fullmatch(
            r"/scholarship/[^/?#]+/?",
            parsed.path,
            re.IGNORECASE,
        )
    )


# ============================================================
# EXACT WMS FIELD EXTRACTION
# ============================================================

FIELD_LABELS = [
    "Eligible Degrees",
    "Funding Type",
    "Deadline",
    "Provider",
    "Eligible Courses",
    "Eligible Nationalities",
    "Scholarship can be taken at",
    "Can Be Taken At",
    "Study At",
    "Updated on",
    "Last Verified On",
    "Overview",
    "Details about",
]


def extract_field(
    text: str,
    field_name: str,
) -> str:

    all_labels = "|".join(
        re.escape(label)
        for label in FIELD_LABELS
        if label.lower() != field_name.lower()
    )

    pattern = re.compile(
        rf"""
        {re.escape(field_name)}
        \s*:?
        \s*
        (.*?)
        (?=
            \s*(?:{all_labels})\s*:?
            |
            \s*Details\s+about
            |
            \s*Shortlist
            |
            \s*Apply\s+Now
            |
            $
        )
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    match = pattern.search(text)

    if not match:
        return ""

    value = clean(match.group(1))

    # Remove UI noise.
    value = re.sub(
        r"\b(?:Shortlist|More Details|Apply Now|Check Eligibility)\b",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return clean(value)


def extract_degree(text: str) -> str:
    return extract_field(
        text,
        "Eligible Degrees",
    )


def extract_funding(text: str) -> str:
    return extract_field(
        text,
        "Funding Type",
    )


def extract_deadline(text: str) -> str:
    return extract_field(
        text,
        "Deadline",
    )


def extract_provider(text: str) -> str:
    return extract_field(
        text,
        "Provider",
    )


def extract_courses(text: str) -> str:
    return extract_field(
        text,
        "Eligible Courses",
    )


def extract_nationality(text: str) -> str:
    return extract_field(
        text,
        "Eligible Nationalities",
    )


def extract_study_location(text: str) -> str:
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

    return clean(value)


# ============================================================
# COUNTRY EXTRACTION
# ============================================================

def normalize_country(value: str) -> str:
    value = normalize(value)

    if not value:
        return ""

    if value in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[value]

    return ""


def countries_from_text(text: str) -> list[str]:
    """
    Extract countries explicitly appearing in a text.
    """

    normalized = normalize(text)

    found: list[str] = []

    # Longest names first to avoid partial matches.
    aliases = sorted(
        COUNTRY_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for alias, country in aliases:

        escaped = re.escape(alias)

        if re.search(
            rf"(?<![a-z]){escaped}(?![a-z])",
            normalized,
            flags=re.IGNORECASE,
        ):
            if country not in found:
                found.append(country)

    return found


def institution_country(
    institution: str,
) -> str:

    normalized = normalize(institution)

    if not normalized:
        return ""

    # Exact match first.
    if normalized in INSTITUTION_COUNTRIES:
        return INSTITUTION_COUNTRIES[normalized]

    # Then substring matching.
    candidates = sorted(
        INSTITUTION_COUNTRIES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for name, country in candidates:
        if name in normalized:
            return country

    return ""


def extract_destination_country(
    study_location: str,
    provider: str,
    title: str,
    page_text: str,
) -> tuple[str, list[str], str]:

    """
    Returns:

    primary_country
    all_detected_countries
    confidence

    Priority:

    1. Explicit country in "Scholarship can be taken at"
    2. Country in provider
    3. Country in title
    4. Known institution -> country
    5. Explicit country in nearby page information
    6. Unknown
    """

    # --------------------------------------------------------
    # 1. Explicit destination field
    # --------------------------------------------------------

    explicit = countries_from_text(
        study_location
    )

    if explicit:
        return (
            explicit[0],
            explicit,
            "high",
        )

    # --------------------------------------------------------
    # 2. Provider
    # --------------------------------------------------------

    provider_countries = countries_from_text(
        provider
    )

    if provider_countries:
        return (
            provider_countries[0],
            provider_countries,
            "high",
        )

    # --------------------------------------------------------
    # 3. Title
    # --------------------------------------------------------

    title_countries = countries_from_text(
        title
    )

    if title_countries:
        return (
            title_countries[0],
            title_countries,
            "medium",
        )

    # --------------------------------------------------------
    # 4. Institution mapping
    # --------------------------------------------------------

    country = institution_country(
        study_location
    )

    if not country:
        country = institution_country(
            provider
        )

    if not country:
        country = institution_country(
            title
        )

    if country:
        return (
            country,
            [country],
            "medium",
        )

    # --------------------------------------------------------
    # 5. Known location phrases
    # --------------------------------------------------------

    location_phrases = [
        ("california", "United States"),
        ("sacramento", "United States"),
        ("new york", "United States"),
        ("massachusetts", "United States"),
        ("texas", "United States"),
        ("florida", "United States"),
        ("edinburgh", "United Kingdom"),
        ("london", "United Kingdom"),
        ("oxford", "United Kingdom"),
        ("cambridge", "United Kingdom"),
        ("dublin", "Ireland"),
        ("paris", "France"),
        ("berlin", "Germany"),
        ("munich", "Germany"),
        ("münchen", "Germany"),
        ("vienna", "Austria"),
        ("amsterdam", "Netherlands"),
        ("rotterdam", "Netherlands"),
        ("brussels", "Belgium"),
        ("helsinki", "Finland"),
        ("stockholm", "Sweden"),
        ("oslo", "Norway"),
        ("copenhagen", "Denmark"),
        ("zurich", "Switzerland"),
        ("zürich", "Switzerland"),
        ("toronto", "Canada"),
        ("vancouver", "Canada"),
        ("montreal", "Canada"),
        ("sydney", "Australia"),
        ("melbourne", "Australia"),
        ("brisbane", "Australia"),
        ("perth", "Australia"),
        ("adelaide", "Australia"),
        ("madrid", "Spain"),
        ("barcelona", "Spain"),
    ]

    location_text = normalize(
        f"{study_location} {provider} {title}"
    )

    for phrase, country in location_phrases:
        if phrase in location_text:
            return (
                country,
                [country],
                "medium",
            )

    # --------------------------------------------------------
    # 6. Do NOT guess from unrelated page-wide countries.
    # --------------------------------------------------------

    return (
        "",
        [],
        "unknown",
    )


# ============================================================
# DEGREE MATCHING
# ============================================================

def degree_match(
    title: str,
    degree_requirement: str,
) -> tuple[str, int, list[str]]:

    text = normalize(
        f"{title} {degree_requirement}"
    )

    if not text:
        return (
            "unknown",
            0,
            ["Degree requirement could not be detected."],
        )

    master = bool(
        re.search(
            r"\bmasters?\b|\bmaster'?s\b|\bmsc\b|\bm\.sc\b",
            text,
        )
    )

    bachelor = bool(
        re.search(
            r"\bbachelors?\b|\bbachelor'?s\b|\bbsc\b|\bb\.sc\b",
            text,
        )
    )

    phd = bool(
        re.search(
            r"\bphd\b|\bph\.d\b|\bdoctorate\b",
            text,
        )
    )

    if master:
        return (
            "eligible",
            30,
            ["Master's degree eligibility detected."],
        )

    if bachelor or phd:
        return (
            "excluded",
            -50,
            ["Scholarship appears to target a different degree level."],
        )

    return (
        "unknown",
        0,
        ["Master's eligibility is unclear."],
    )


# ============================================================
# FIELD MATCHING
# ============================================================

DIRECT_FIELDS = [
    "computer science",
    "computer sciences",
    "information technology",
    "information technologies",
    "information systems",
    "software engineering",
    "computer engineering",
    "informatics",
    "computing",
    "computer applications",
]

RELATED_FIELDS = [
    "artificial intelligence",
    "machine learning",
    "data science",
    "data engineering",
    "cyber security",
    "cybersecurity",
    "software development",
    "cloud computing",
    "network security",
    "information security",
    "web technologies",
    "computer networks",
]


def field_match(
    title: str,
    courses: str,
) -> tuple[str, int, list[str]]:

    text = normalize(
        f"{title} {courses}"
    )

    direct_hits = [
        field
        for field in DIRECT_FIELDS
        if field in text
    ]

    related_hits = [
        field
        for field in RELATED_FIELDS
        if field in text
    ]

    # "IT" needs word boundaries so it doesn't match random words.
    if re.search(r"\bit\b", text):
        direct_hits.append("IT")

    if direct_hits:
        return (
            "direct",
            30,
            [
                "Computer Science / IT field match detected.",
                f"Matched field terms: {', '.join(unique(direct_hits))}.",
            ],
        )

    if related_hits:
        return (
            "related",
            18,
            [
                "Related technology field detected.",
                f"Related terms: {', '.join(unique(related_hits))}.",
            ],
        )

    # Generic university courses are not enough to claim a match.
    return (
        "unknown",
        0,
        [
            "Computer Science / IT field match could not be confirmed."
        ],
    )


# ============================================================
# NATIONALITY MATCHING
# ============================================================

def nationality_match(
    nationality_requirement: str,
) -> tuple[str, int, list[str]]:

    text = normalize(
        nationality_requirement
    )

    if not text:
        return (
            "unknown",
            0,
            ["Nationality requirement could not be detected."],
        )

    # Open to everybody.
    if any(
        phrase in text
        for phrase in [
            "open to all nationals",
            "open to all nationalities",
            "all nationals",
            "all nationalities",
            "open to international students",
            "open to all international students",
            "any nationality",
            "all international students",
            "open for all nationals",
        ]
    ):
        return (
            "eligible",
            25,
            ["Scholarship appears open to all nationals/international students."],
        )

    # Benin explicitly included.
    if (
        "benin" in text
        or "beninese" in text
    ):
        return (
            "eligible",
            25,
            ["Benin/Beninese applicants are explicitly included."],
        )

    # African eligibility.
    if any(
        phrase in text
        for phrase in [
            "african nationals",
            "african students",
            "students from africa",
            "citizens of african countries",
            "nationals of african countries",
        ]
    ):
        return (
            "eligible",
            25,
            ["Eligibility includes African applicants."],
        )

    # Explicit exclusions / restrictive nationality.
    restricted_patterns = [
        "only indian nationals",
        "indian nationals only",
        "only indian citizens",
        "indian citizens only",
        "open to indian nationals only",
        "open to indian citizens only",
        "citizens of india only",
        "residents of india only",
        "indian students only",
    ]

    if any(
        phrase in text
        for phrase in restricted_patterns
    ):
        return (
            "excluded",
            -60,
            [
                "Scholarship is restricted to Indian applicants."
            ],
        )

    # If a named nationality appears but isn't Benin,
    # don't automatically call it ineligible.
    named_countries = countries_from_text(text)

    if named_countries:
        return (
            "unknown",
            0,
            [
                "Scholarship has a nationality restriction that requires manual confirmation.",
                f"Countries mentioned: {', '.join(named_countries)}.",
            ],
        )

    return (
        "unknown",
        0,
        ["Nationality eligibility requires manual confirmation."],
    )


# ============================================================
# CGPA EXTRACTION
# ============================================================

def extract_cgpa_requirements(
    text: str,
) -> list[str]:

    patterns = [
        r"""
        (?:
            minimum|min|required|at\s+least
        )
        \s*
        (?:
            cumulative\s+
        )?
        (?:
            cgpa|gpa
        )
        \s*
        (?:
            of|:|is
        )?
        \s*
        \d+(?:\.\d+)?
        \s*
        (?:
            /|out\s+of
        )
        \s*
        \d+(?:\.\d+)?
        """,

        r"""
        (?:
            cgpa|gpa
        )
        \s*
        (?:
            of|:|is
        )?
        \s*
        \d+(?:\.\d+)?
        \s*
        (?:
            /|out\s+of
        )
        \s*
        \d+(?:\.\d+)?
        """,

        r"""
        (?:
            minimum|min|required|at\s+least
        )
        \s+
        \d+(?:\.\d+)?
        \s*
        %
        """,
    ]

    results: list[str] = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        for match in matches:
            value = clean(match)

            if value and value not in results:
                results.append(value)

    return results[:10]


def cgpa_match(
    requirements: list[str],
) -> tuple[str, int, list[str]]:

    if not requirements:
        return (
            "unknown",
            0,
            ["No explicit CGPA requirement detected."],
        )

    applicant_ratio = (
        STUDENT_PROFILE["cgpa"]
        / STUDENT_PROFILE["cgpa_scale"]
    )

    for requirement in requirements:

        match = re.search(
            r"(\d+(?:\.\d+)?)\s*"
            r"(?:/|out\s+of)\s*"
            r"(\d+(?:\.\d+)?)",
            normalize(requirement),
        )

        if not match:
            continue

        required = float(match.group(1))
        scale = float(match.group(2))

        required_ratio = required / scale

        if applicant_ratio >= required_ratio:
            return (
                "eligible",
                10,
                [
                    f"CGPA {STUDENT_PROFILE['cgpa']}/"
                    f"{STUDENT_PROFILE['cgpa_scale']} "
                    f"meets {requirement}."
                ],
            )

        return (
            "excluded",
            -35,
            [
                f"CGPA {STUDENT_PROFILE['cgpa']}/"
                f"{STUDENT_PROFILE['cgpa_scale']} "
                f"is below {requirement}."
            ],
        )

    return (
        "unknown",
        0,
        [
            "A CGPA/GPA statement was detected but could not be interpreted automatically."
        ],
    )


# ============================================================
# DESTINATION MATCHING
# ============================================================

def destination_match(
    destination_country: str,
) -> tuple[str, int, list[str]]:

    if not destination_country:
        return (
            "unknown",
            0,
            ["Destination country could not be determined reliably."],
        )

    preferred = {
        normalize(country)
        for country in STUDENT_PROFILE[
            "preferred_destinations"
        ]
    }

    if normalize(destination_country) in preferred:
        return (
            "preferred",
            10,
            [
                f"Destination matches your preferred country: "
                f"{destination_country}."
            ],
        )

    return (
        "not_preferred",
        0,
        [
            f"Destination is {destination_country}, "
            "which is outside your preferred-country list."
        ],
    )


# ============================================================
# DEADLINE
# ============================================================

DEADLINE_FORMATS = [
    "%d %b, %Y",
    "%d %B, %Y",
    "%d %b %Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%b %d, %Y",
]


def parse_deadline(
    deadline: str,
) -> datetime | None:

    if not deadline:
        return None

    value = clean(deadline)

    # Remove surrounding UI text.
    value = re.sub(
        r"\b(?:Expires in|Deadline:)\b",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = clean(value)

    for fmt in DEADLINE_FORMATS:
        try:
            return datetime.strptime(
                value,
                fmt,
            )
        except ValueError:
            continue

    # More forgiving extraction.
    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"(?:\s*,?)\s+(\d{4})\b",
        value,
        flags=re.IGNORECASE,
    )

    if match:
        candidate = (
            f"{match.group(1)} "
            f"{match.group(2)} "
            f"{match.group(3)}"
        )

        for fmt in [
            "%d %b %Y",
            "%d %B %Y",
        ]:
            try:
                return datetime.strptime(
                    candidate,
                    fmt,
                )
            except ValueError:
                pass

    return None


def deadline_status(
    deadline: str,
) -> tuple[str, list[str]]:

    if not deadline:
        return (
            "unknown",
            ["No clear deadline detected."],
        )

    parsed = parse_deadline(
        deadline
    )

    if parsed is None:

        if "expired" in normalize(deadline):
            return (
                "expired",
                [f"Deadline appears expired: {deadline}."],
            )

        return (
            "unknown",
            [
                f"Deadline was found but could not be parsed automatically: {deadline}."
            ],
        )

    if parsed.date() < datetime.now().date():
        return (
            "expired",
            [f"Deadline has passed: {deadline}."],
        )

    return (
        "active",
        [f"Deadline: {deadline}."],
    )


# ============================================================
# OVERALL MATCH SCORE
# ============================================================

def calculate_match(
    title: str,
    degree: str,
    courses: str,
    nationality: str,
    destination_country: str,
    deadline: str,
    cgpa_requirements: list[str],
    funding: str,
) -> dict[str, Any]:

    score = 0

    reasons: list[str] = []
    warnings: list[str] = []

    # --------------------------------------------------------
    # Degree
    # --------------------------------------------------------

    degree_status, degree_points, degree_messages = degree_match(
        title,
        degree,
    )

    score += degree_points

    if degree_points > 0:
        reasons.extend(degree_messages)
    else:
        warnings.extend(degree_messages)

    # --------------------------------------------------------
    # Field
    # --------------------------------------------------------

    field_status, field_points, field_messages = field_match(
        title,
        courses,
    )

    score += field_points

    if field_points > 0:
        reasons.extend(field_messages)
    else:
        warnings.extend(field_messages)

    # --------------------------------------------------------
    # Nationality
    # --------------------------------------------------------

    nationality_status, nationality_points, nationality_messages = (
        nationality_match(nationality)
    )

    score += nationality_points

    if nationality_status == "eligible":
        reasons.extend(nationality_messages)

    elif nationality_status == "excluded":
        warnings.extend(nationality_messages)

    else:
        warnings.extend(nationality_messages)

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    destination_status, destination_points, destination_messages = (
        destination_match(destination_country)
    )

    score += destination_points

    if destination_status == "preferred":
        reasons.extend(destination_messages)
    else:
        warnings.extend(destination_messages)

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    cgpa_status, cgpa_points, cgpa_messages = cgpa_match(
        cgpa_requirements
    )

    score += cgpa_points

    if cgpa_status == "eligible":
        reasons.extend(cgpa_messages)

    elif cgpa_status == "excluded":
        warnings.extend(cgpa_messages)

    else:
        warnings.extend(cgpa_messages)

    # --------------------------------------------------------
    # Funding
    # --------------------------------------------------------

    if funding:
        reasons.append(
            f"Funding information: {funding}"
        )

    # --------------------------------------------------------
    # Deadline
    # --------------------------------------------------------

    deadline_state, deadline_messages = deadline_status(
        deadline
    )

    if deadline_state == "expired":
        score -= 25
        warnings.extend(deadline_messages)

    elif deadline_state == "active":
        reasons.extend(deadline_messages)

    else:
        warnings.extend(deadline_messages)

    # --------------------------------------------------------
    # Clamp score
    # --------------------------------------------------------

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    if degree_status == "excluded":
        status = "likely_not_eligible"

    elif nationality_status == "excluded":
        status = "likely_not_eligible"

    elif cgpa_status == "excluded":
        status = "likely_not_eligible"

    elif deadline_state == "expired":
        status = "expired"

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

    found: list[str] = []

    for link in context.soup.find_all(
        "a",
        href=True,
    ):

        href = link.get("href")

        if not isinstance(href, str):
            continue

        url = urljoin(
            context.request.url,
            href,
        )

        parsed = urlparse(url)

        if parsed.netloc.lower() not in WMS_DOMAINS:
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
        f"Found {len(found)} individual scholarship pages."
    )

    if found:
        await context.add_requests(
            found
        )

        Actor.log.info(
            f"Queued {len(found)} scholarship pages."
        )


# ============================================================
# INDIVIDUAL SCHOLARSHIP
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

    page_text = get_page_text(
        context
    )

    # --------------------------------------------------------
    # Extract WMS fields
    # --------------------------------------------------------

    degree = extract_degree(
        page_text
    )

    funding = extract_funding(
        page_text
    )

    deadline = extract_deadline(
        page_text
    )

    provider = extract_provider(
        page_text
    )

    courses = extract_courses(
        page_text
    )

    nationality = extract_nationality(
        page_text
    )

    study_location = extract_study_location(
        page_text
    )

    # --------------------------------------------------------
    # CGPA
    # --------------------------------------------------------

    cgpa_requirements = extract_cgpa_requirements(
        page_text
    )

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    (
        destination_country,
        detected_countries,
        destination_confidence,
    ) = extract_destination_country(
        study_location=study_location,
        provider=provider,
        title=title,
        page_text=page_text,
    )

    # --------------------------------------------------------
    # Strict profile matching (v2)
    # --------------------------------------------------------

    match = strict_match(
        title=title,
        degree=degree,
        courses=courses,
        nationality=nationality,
        destination=destination_country,
        deadline=deadline,
        cgpa_requirements=cgpa_requirements,
        funding=funding,
        page_text=page_text,
    )

    # --------------------------------------------------------
    # Record
    # --------------------------------------------------------

    record = {
        "record_type": "individual_scholarship",

        "title": title,

        "url": url,

        "source_domain": urlparse(url).netloc,

        "match_score": match["match_score"],

        "match_status": match["match_status"],

        "reasons": match["reasons"],

        "warnings": match["warnings"],

        # Strict profile decision details.
        "recommendation": match["recommendation"],
        "profile_version": match["profile_version"],
        "profile_rule": match["profile_rule"],
        "degree_match": match["degree_match"],
        "field_match": match["field_match"],
        "nationality_match": match["nationality_match"],
        "funding_status": match["funding_status"],
        "destination_match": match["destination_match"],
        "application_from_abroad": match["application_from_abroad"],
        "cgpa_match": match["cgpa_match"],
        "deadline_state": match["deadline_state"],

        "student_profile": STUDENT_PROFILE,

        # --------------------------------------------
        # Degree
        # --------------------------------------------

        "degree_requirements": {
            "raw": degree,
            "target": "Master",
        },

        # --------------------------------------------
        # Field
        # --------------------------------------------

        "field_requirements": {
            "raw": courses,
            "target": "Computer Science / IT",
        },

        # --------------------------------------------
        # Nationality
        # --------------------------------------------

        "nationality_requirements": {
            "raw": nationality,
            "student_nationality": "Benin",
        },

        # --------------------------------------------
        # CGPA
        # --------------------------------------------

        "cgpa_requirements": cgpa_requirements,

        # --------------------------------------------
        # Destination
        # --------------------------------------------

        "destination": destination_country,

        # Keep the actual WMS value.
        "destination_raw": study_location,

        "destination_countries_detected": detected_countries,

        "destination_confidence": destination_confidence,

        # --------------------------------------------
        # Provider
        # --------------------------------------------

        "provider": provider,

        # --------------------------------------------
        # Deadline
        # --------------------------------------------

        "deadlines": (
            [deadline]
            if deadline
            else []
        ),

        "deadline_status": deadline_status(
            deadline
        )[0],

        # --------------------------------------------
        # Funding
        # --------------------------------------------

        "funding": funding,

        # --------------------------------------------
        # Page headings
        # --------------------------------------------

        "h1s": h1s,

        "h2s": h2s,

        "h3s": h3s,
    }

    await context.push_data(
        record
    )

    Actor.log.info(
        "RESULT | "
        f"{title} | "
        f"score={match['match_score']} | "
        f"status={match['match_status']} | "
        f"funding={match['funding_status']} | "
        f"field={match['field_match']} | "
        f"abroad={match['application_from_abroad']} | "
        f"country={destination_country or 'UNKNOWN'}"
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
