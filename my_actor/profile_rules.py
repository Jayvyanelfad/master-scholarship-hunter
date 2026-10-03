"""Strict profile matching rules for Master Scholarship Hunter."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


# ============================================================
# STUDENT PROFILE
# ============================================================

STUDENT_PROFILE = {
    "nationality": "Benin",
    "current_country": "India",
    "degree": "Master",
    "field": "Computer Science / IT / AI",
    "cgpa": 6.0,
    "cgpa_scale": 10.0,
    "expected_btech_completion": "2027-06",
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
        "Ireland",
        "Canada",
        "Australia",
        "Austria",
        "Switzerland",
        "Luxembourg",
        "Japan",
        "Singapore",
    ],
    "full_funding_only": True,
}


# ============================================================
# FIELD DEFINITIONS
# ============================================================

DIRECT_FIELD_TERMS = (
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
)

AI_FIELD_TERMS = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "generative ai",
    "agentic ai",
    "ai engineering",
    "intelligent systems",
    "natural language processing",
    "nlp",
    "computer vision",
    "robotics",
    "autonomous systems",
    "computational intelligence",
    "data science",
    "data engineering",
    "big data",
)

RELATED_FIELD_TERMS = (
    "cyber security",
    "cybersecurity",
    "information security",
    "cloud computing",
    "distributed systems",
    "human-computer interaction",
)


TARGET_COUNTRIES = {
    x.lower()
    for x in STUDENT_PROFILE["preferred_destinations"]
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def _norm(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip().lower()


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for value in values:
        value = re.sub(
            r"\s+",
            " ",
            str(value or ""),
        ).strip()

        if value and value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)

    return out


def _contains_any(
    text: str,
    terms: tuple[str, ...],
) -> list[str]:
    return [
        term
        for term in terms
        if term in text
    ]


# ============================================================
# PAGE CONTEXT
# ============================================================

def _extract_overview_context(
    page_text: str,
) -> str:
    text = re.sub(
        r"\s+",
        " ",
        page_text or "",
    ).strip()

    if not text:
        return ""

    lower = text.lower()

    starts = [
        lower.find("overview"),
        lower.find("eligibility criteria"),
        lower.find("eligibility requirements"),
    ]

    starts = [
        x
        for x in starts
        if x >= 0
    ]

    if not starts:
        return text[:7000]

    start = min(starts)

    return text[
        start:start + 9000
    ]


# ============================================================
# DEGREE MATCHING
# ============================================================

def _degree(
    text: str,
) -> tuple[str, list[str]]:

    t = _norm(text)

    master = bool(
        re.search(
            r"\bmaster(?:'s|s)?\b"
            r"|\bmsc\b"
            r"|\bm\.sc\b",
            t,
        )
    )

    phd = bool(
        re.search(
            r"\bph\.?\s*d\.?\b"
            r"|\bdoctorate\b"
            r"|\bdoctoral\b",
            t,
        )
    )

    bachelor = bool(
        re.search(
            r"\bbachelor(?:'s|s)?\b"
            r"|\bbsc\b"
            r"|\bb\.sc\b",
            t,
        )
    )

    if master:
        return (
            "eligible",
            ["Master's eligibility detected."],
        )

    if phd or bachelor:
        return (
            "excluded",
            [
                "No Master's eligibility was detected; "
                "the opportunity appears to target another "
                "degree level."
            ],
        )

    return (
        "unknown",
        [
            "Master's eligibility could not be confirmed."
        ],
    )


# ============================================================
# FIELD MATCHING
# ============================================================

def _field(
    title: str,
    courses: str,
    page_text: str,
) -> tuple[str, list[str]]:

    context = " ".join(
        [
            _norm(title),
            _norm(courses),
            _norm(
                _extract_overview_context(
                    page_text
                )
            ),
        ]
    )

    direct = _contains_any(
        context,
        DIRECT_FIELD_TERMS,
    )

    ai = _contains_any(
        context,
        AI_FIELD_TERMS,
    )

    related = _contains_any(
        context,
        RELATED_FIELD_TERMS,
    )

    if direct or ai:

        hits = _unique(
            direct + ai
        )

        return (
            "eligible",
            [
                "Computer/IT/AI-related field detected.",
                (
                    "Matched field terms: "
                    + ", ".join(hits)
                    + "."
                ),
            ],
        )

    if related:

        return (
            "possible",
            [
                (
                    "A related "
                    "computing/technology "
                    "field was detected."
                ),
                (
                    "Related terms: "
                    + ", ".join(
                        _unique(related)
                    )
                    + "."
                ),
            ],
        )

    return (
        "excluded",
        [
            "Computer Science / IT / AI relevance "
            "could not be confirmed."
        ],
    )


# ============================================================
# NATIONALITY MATCHING
# ============================================================

def _nationality(
    requirement: str,
) -> tuple[str, list[str]]:

    t = _norm(requirement)

    if not t:
        return (
            "unknown",
            [
                "Nationality eligibility "
                "could not be confirmed."
            ],
        )

    if any(
        x in t
        for x in (
            "open to all nationals",
            "open to all nationalities",
            "all nationals",
            "all nationalities",
            "any nationality",
            "open to international students",
            "open to all international students",
            "all international students",
        )
    ):
        return (
            "eligible",
            [
                "Open to international/all nationalities."
            ],
        )

    if (
        "benin" in t
        or "beninese" in t
    ):
        return (
            "eligible",
            [
                "Benin/Beninese applicants "
                "are explicitly eligible."
            ],
        )

    restrictive_india = (
        "indian nationals only",
        "only indian nationals",
        "indian citizens only",
        "only indian citizens",
        "citizens of india only",
        "residents of india only",
        "indian students only",
    )

    if any(
        x in t
        for x in restrictive_india
    ):
        return (
            "excluded",
            [
                "The scholarship is restricted "
                "to Indian applicants."
            ],
        )

    return (
        "unknown",
        [
            "Nationality restriction requires "
            "verification for a Beninese applicant."
        ],
    )


# ============================================================
# FUNDING MATCHING
# ============================================================

def _funding(
    funding: str,
    page_text: str,
) -> tuple[str, list[str]]:
    """
    Strict rule:
    'Full Funding' on a listing is not enough.

    We require evidence that the award covers
    major cost components such as tuition plus
    living/stipend/maintenance.
    """

    t = _norm(
        " ".join(
            [
                funding,
                _extract_overview_context(
                    page_text
                ),
                page_text[:12000],
            ]
        )
    )

    if any(
        x in t
        for x in (
            "accommodation scholarship",
            "accommodation bursary",
            "accommodation only",
            "housing only",
            "book allowance only",
            "travel grant only",
            "tuition waiver only",
            "tuition discount",
            "partial funding",
            "partial scholarship",
            "bursary",
        )
    ):
        return (
            "excluded",
            [
                "Funding is partial, a bursary, "
                "or limited to a specific expense."
            ],
        )

    full_phrase = any(
        x in t
        for x in (
            "fully funded",
            "full funding",
            "full scholarship",
            "fully-funded",
        )
    )

    tuition = any(
        x in t
        for x in (
            "full tuition",
            "tuition fees",
            "tuition fee",
            "covers tuition",
            "tuition and",
            "tuition +",
        )
    )

    living = any(
        x in t
        for x in (
            "living expenses",
            "living allowance",
            "monthly stipend",
            "monthly allowance",
            "maintenance allowance",
            "maintenance stipend",
            "stipend",
            "cost of living",
        )
    )

    travel = any(
        x in t
        for x in (
            "airfare",
            "flight allowance",
            "travel allowance",
            "travel costs",
        )
    )

    # Strongest signal:
    # explicit full funding + tuition + living support.
    if (
        full_phrase
        and tuition
        and living
    ):

        evidence = [
            "Explicit full-funding language detected.",
            "Tuition coverage detected.",
            "Living/stipend support detected.",
        ]

        if travel:
            evidence.append(
                "Travel support also detected."
            )

        return (
            "verified_full",
            evidence,
        )

    # Some pages describe the package
    # without saying "fully funded".
    if tuition and living:

        evidence = [
            "Tuition coverage detected.",
            "Living/stipend support detected.",
        ]

        if travel:
            evidence.append(
                "Travel support also detected."
            )

        return (
            "verified_full",
            evidence,
        )

    # Full funding label alone is not enough.
    if full_phrase:

        return (
            "unknown",
            [
                "The page says full funding, "
                "but the actual tuition + living "
                "coverage could not be verified."
            ],
        )

    return (
        "excluded",
        [
            "Full funding could not be verified "
            "from the scholarship information."
        ],
    )


# ============================================================
# DESTINATION MATCHING
# ============================================================

def _destination(
    destination: str,
) -> tuple[str, list[str]]:

    country = _norm(destination)

    if not country:
        return (
            "unknown",
            [
                "Destination country could not "
                "be determined."
            ],
        )

    if country in TARGET_COUNTRIES:
        return (
            "eligible",
            [
                (
                    "Destination matches target "
                    f"country: {destination}."
                )
            ],
        )

    return (
        "excluded",
        [
            (
                "Destination is outside the "
                "target-country list: "
                f"{destination}."
            )
        ],
    )


# ============================================================
# APPLYING FROM ABROAD
# ============================================================

def _abroad_application(
    destination: str,
    page_text: str,
) -> tuple[str, list[str]]:

    t = _norm(page_text)
    dest = _norm(destination)

    if not dest:
        return (
            "unknown",
            [
                "Applicant-location requirement "
                "cannot be assessed without "
                "a destination."
            ],
        )

    # Explicit onshore/current-resident restrictions.
    patterns = (
        r"\bcurrently\s+(?:living|residing|studying)\s+in\s+",
        r"\bcurrently\s+(?:living|residing|studying)\s+at\s+",
        r"\bmust\s+(?:be|already be)\s+(?:living|residing|studying)\s+in\s+",
        r"\bmust\s+(?:be|already be)\s+enrolled\s+(?:at|in)\s+",
        r"\bcurrent\s+(?:students|student)\s+(?:of|at)\s+",
        r"\bexisting\s+(?:students|student)\s+(?:of|at)\s+",
        r"\bonshore\s+(?:applicants|students)\b",
        r"\bon-shore\s+(?:applicants|students)\b",
        r"\bapplicants\s+(?:already|currently)\s+in\s+",
    )

    matched = [
        p
        for p in patterns
        if re.search(p, t)
    ]

    if matched:

        # "New commencing" students are not
        # automatically onshore-only.
        if (
            "new commencing" in t
            or "newly commencing" in t
        ):
            return (
                "eligible",
                [
                    "New/commencing international "
                    "applicants are mentioned; no clear "
                    "onshore-only restriction was detected."
                ],
            )

        return (
            "excluded",
            [
                "The scholarship appears restricted "
                "to people already studying/living/"
                "enrolled in the destination or institution."
            ],
        )

    # Explicit international-student language
    # without an onshore restriction.
    if (
        "international students" in t
        and not any(
            x in t
            for x in (
                "currently in",
                "currently residing",
                "onshore",
                "already enrolled",
            )
        )
    ):
        return (
            "eligible",
            [
                "International applicants are mentioned "
                "and no clear onshore-only restriction "
                "was detected."
            ],
        )

    return (
        "unknown",
        [
            "Whether a student applying from outside "
            "the destination can apply could not "
            "be confirmed."
        ],
    )


# ============================================================
# CGPA MATCHING
# ============================================================

def _cgpa(
    cgpa_requirements: list[str],
) -> tuple[str, list[str]]:

    if not cgpa_requirements:
        return (
            "unknown",
            [
                "No explicit CGPA requirement "
                "was detected."
            ],
        )

    applicant_ratio = (
        STUDENT_PROFILE["cgpa"]
        / STUDENT_PROFILE["cgpa_scale"]
    )

    for req in cgpa_requirements:

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*"
            r"(?:/|out\s+of)\s*"
            r"(\d+(?:\.\d+)?)",
            _norm(req),
        )

        if not m:
            continue

        required_ratio = (
            float(m.group(1))
            / float(m.group(2))
        )

        if applicant_ratio >= required_ratio:
            return (
                "eligible",
                [
                    (
                        f"CGPA "
                        f"{STUDENT_PROFILE['cgpa']}/"
                        f"{STUDENT_PROFILE['cgpa_scale']} "
                        f"meets {req}."
                    )
                ],
            )

        return (
            "excluded",
            [
                (
                    f"CGPA "
                    f"{STUDENT_PROFILE['cgpa']}/"
                    f"{STUDENT_PROFILE['cgpa_scale']} "
                    f"is below {req}."
                )
            ],
        )

    return (
        "unknown",
        [
            "A GPA/CGPA requirement was detected "
            "but could not be interpreted automatically."
        ],
    )


# ============================================================
# STRICT MATCH
# ============================================================

def strict_match(
    *,
    title: str,
    degree: str,
    courses: str,
    nationality: str,
    destination: str,
    deadline: str,
    cgpa_requirements: list[str],
    funding: str,
    page_text: str,
) -> dict[str, Any]:

    degree_status, degree_reasons = _degree(
        " ".join(
            [
                title,
                degree,
            ]
        )
    )

    field_status, field_reasons = _field(
        title,
        courses,
        page_text,
    )

    nationality_status, nationality_reasons = _nationality(
        nationality
    )

    funding_status, funding_reasons = _funding(
        funding,
        page_text,
    )

    destination_status, destination_reasons = _destination(
        destination
    )

    abroad_status, abroad_reasons = _abroad_application(
        destination,
        page_text,
    )

    cgpa_status, cgpa_reasons = _cgpa(
        cgpa_requirements
    )

    hard_failures: list[str] = []

    # Degree
    if degree_status != "eligible":
        hard_failures.extend(
            degree_reasons
        )

    # Field
    if field_status != "eligible":
        hard_failures.extend(
            field_reasons
        )

    # Nationality
    if nationality_status in (
        "excluded",
        "unknown",
    ):
        hard_failures.extend(
            nationality_reasons
        )

    # Funding
    if funding_status != "verified_full":
        hard_failures.extend(
            funding_reasons
        )

    # Destination
    if destination_status != "eligible":
        hard_failures.extend(
            destination_reasons
        )

    # Applying from abroad
    if abroad_status in (
        "excluded",
        "unknown",
    ):
        hard_failures.extend(
            abroad_reasons
        )

    # CGPA
    if cgpa_status == "excluded":
        hard_failures.extend(
            cgpa_reasons
        )

    # ========================================================
    # DEADLINE
    # ========================================================

    deadline_state = "unknown"
    deadline_reasons: list[str] = []

    if deadline:

        parsed = None

        for fmt in (
            "%d %b, %Y",
            "%d %B, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ):

            try:
                parsed = datetime.strptime(
                    deadline.strip(),
                    fmt,
                )
                break

            except ValueError:
                pass

        if parsed is not None:

            if (
                parsed.date()
                < datetime.now().date()
            ):

                deadline_state = "expired"

                deadline_reasons = [
                    (
                        "Deadline has passed: "
                        f"{deadline}."
                    )
                ]

                hard_failures.extend(
                    deadline_reasons
                )

            else:

                deadline_state = "active"

                deadline_reasons = [
                    f"Deadline: {deadline}."
                ]

        else:

            deadline_state = "unknown"

            deadline_reasons = [
                (
                    "Deadline was detected but "
                    "could not be parsed: "
                    f"{deadline}."
                )
            ]

    else:

        deadline_reasons = [
            "No clear deadline detected."
        ]

    # ========================================================
    # FINAL RESULT
    # ========================================================

    reasons = _unique(
        degree_reasons
        + field_reasons
        + nationality_reasons
        + funding_reasons
        + destination_reasons
        + abroad_reasons
        + cgpa_reasons
        + deadline_reasons
    )

    hard_failures = _unique(
        hard_failures
    )

    # Only opportunities that pass ALL
    # hard filters enter the daily email.
    if not hard_failures:

        status = "strong_match"
        score = 100

    else:

        status = "rejected"
        score = 0

    return {
        "match_score": score,
        "match_status": status,
        "recommendation": (
            "include"
            if status == "strong_match"
            else "exclude"
        ),
        "reasons": reasons,
        "warnings": hard_failures,
        "degree_match": degree_status,
        "field_match": field_status,
        "nationality_match": nationality_status,
        "funding_status": funding_status,
        "destination_match": destination_status,
        "application_from_abroad": abroad_status,
        "cgpa_match": cgpa_status,
        "deadline_state": deadline_state,
        "profile_version": "strict-v2",
        "profile_rule": (
            "Master's only + full funding only + "
            "CS/IT/AI + Benin eligible + target "
            "country + apply from abroad"
        ),
    }