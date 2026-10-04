"""Deterministic, evidence-first eligibility rules."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

STUDENT_PROFILE = {
    "nationality": "Benin", "current_country": "India", "current_study_location": "India",
    "degree": "Master", "field": "Computer Science / IT / AI",
    "cgpa": 6.0, "cgpa_scale": 10.0, "expected_btech_completion": "2027-06",
    "preferred_destinations": ["Germany", "France", "Netherlands", "Belgium", "Finland", "Sweden", "Norway", "Denmark", "United Kingdom", "Ireland", "Canada", "Australia", "Austria", "Switzerland", "Luxembourg", "Japan", "Singapore"],
    "full_funding_only": True,
}
TARGET_COUNTRIES = {country.lower() for country in STUDENT_PROFILE["preferred_destinations"]}
DIRECT_FIELD_TERMS = ("computer science", "computer sciences", "information technology", "information systems", "software engineering", "computer engineering", "informatics", "computing", "artificial intelligence", "machine learning", "deep learning", "generative ai", "agentic ai", "ai engineering", "intelligent systems", "natural language processing", "nlp", "computer vision", "robotics", "autonomous systems", "data science", "data engineering", "big data")
RELATED_FIELD_TERMS = ("cyber security", "cybersecurity", "information security", "cloud computing", "distributed systems", "computational science", "data analytics", "electrical and computer engineering")
UNRELATED_FIELD_TERMS = ("education", "history", "law", "medicine", "nursing", "public health", "agriculture", "indigenous studies", "social work")

# Explicit denials or caps that prove an award is not full funding, even when
# the surrounding text uses word "scholarship". Checked before any positive
# funding evidence so a denial is never overridden by a vague label.
EXPLICIT_PARTIAL_TERMS = (
    "tuition only", "tuition waiver only", "tuition fees only", "tuition fee only",
    "tuition discount", "partial tuition",
    "partial funding", "bursary", "accommodation only", "meal allowance", "small grant",
    "not a full-tuition scholarship", "not a full tuition scholarship",
    "not full tuition", "not a full scholarship", "not fully funded",
    "not fully-funded", "not full funding", "not living costs", "excluding living costs",
)
PARTIAL_WAIVER_PERCENT_PATTERN = re.compile(
    r"(?:tuition|fee) (?:fee )?waiver of \d+ percent|\d+ percent (?:tuition|fee) waiver"
)
# Fixed-amount phrasing ("amounts to EUR 5,000", "one-off payment") proves a
# capped award. It is only applied when tuition+living coverage is NOT both
# verified, so a fully described package is never downgraded by this rule.
CAPPED_AWARD_TERMS = ("amounts to", "one-off", "one-time payment", "one time payment", "lump sum")
TUITION_EVIDENCE_TERMS = (
    "tuition fees", "tuition fee", "full tuition", "covers tuition", "tuition coverage",
    "participation costs", "full fee waiver", "tuition waiver", "tuition exempt", "fees waived",
    "exemption of tuition", "exemption from tuition",
)
LIVING_EVIDENCE_TERMS = (
    "living expenses", "living allowance", "monthly stipend", "monthly allowance",
    "maintenance allowance", "maintenance stipend", "cost of living", "stipend",
)
MONTHLY_PAYMENT_PATTERN = re.compile(r"(?:[€£$¥]|eur|usd|jpy|gbp|chf|sek|nok|dkk|cad|aud|sgd)\s?[\d,.]+(?:\s*(?:～|~|-|–|to)\s*(?:[€£$¥]|eur|usd|jpy|gbp|chf|sek|nok|dkk|cad|aud|sgd)?\s?[\d,.]+)?\s*(?:per|a|/)\s*month", re.I)

# Terms proving the applicant may reside outside the destination country are
# handled in analyze_application_location. Terms proving residence inside a
# closed eligible-country set is required are matched per-adapter through
# analyze_residence, because only the adapter knows the actual country list.
RESIDENCE_REQUIREMENT_HINTS = ("must reside", "reside in any of", "reside in one of", "resident in one of")


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return _text(value).lower()


def _evidence(claim: str, url: str, source_type: str, confidence: str) -> dict[str, str]:
    return {"claim": claim, "source_url": url, "source_type": source_type, "confidence": confidence}


def _has(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def analyze_degree(value: str, url: str, source_type: str) -> tuple[str, list[dict[str, str]]]:
    text = _norm(value)
    if re.search(r"already completed (?:their|a|the)?\s*master|completed [^.]{0,40}master'?s degree", text):
        return "excluded", [_evidence("Structured degree field requires an already-completed Master's degree (post-Master's/doctoral track).", url, source_type, "high")]
    master = bool(re.search(r"\bmaster(?:'s|s)?\b|\bm\.?sc\b", text))
    excluded = bool(re.search(r"\bph\.?d\b|\bdoctoral\b|\bdoctorate\b|\bbachelor(?:'s|s)?\b|\bdiploma\b|\bcertificate\b|\bpostdoctoral\b", text))
    if master:
        return "eligible", [_evidence("Structured degree field includes Master's study.", url, source_type, "high")]
    if excluded:
        return "excluded", [_evidence("Structured degree field does not establish Master's eligibility.", url, source_type, "high")]
    return "unknown", [_evidence("No structured Master's eligibility was available.", url, source_type, "low")]


def analyze_field(value: str, url: str, source_type: str) -> tuple[str, list[dict[str, str]]]:
    text = _norm(value)
    direct, related, unrelated = _has(text, DIRECT_FIELD_TERMS), _has(text, RELATED_FIELD_TERMS), _has(text, UNRELATED_FIELD_TERMS)
    if direct:
        return "eligible", [_evidence(f"Scholarship field is computing-related: {', '.join(direct)}.", url, source_type, "high")]
    if unrelated and not related:
        return "excluded", [_evidence(f"Scholarship field is unrelated to computing: {', '.join(unrelated)}.", url, source_type, "high")]
    if related:
        return "possible", [_evidence(f"Field is adjacent to computing and needs programme-level confirmation: {', '.join(related)}.", url, source_type, "medium")]
    return "unknown", [_evidence("No scholarship-specific computing field was verified.", url, source_type, "low")]


def analyze_funding(value: str, url: str, source_type: str) -> tuple[str, list[dict[str, str]]]:
    text = _norm(value)
    if _has(text, EXPLICIT_PARTIAL_TERMS) or PARTIAL_WAIVER_PERCENT_PATTERN.search(text) or re.search(r"\b(?:25|50|75)%\b", text):
        return "excluded", [_evidence("Benefits are explicitly partial, capped, or denied full funding.", url, source_type, "high")]
    tuition = any(term in text for term in TUITION_EVIDENCE_TERMS)
    living = any(term in text for term in LIVING_EVIDENCE_TERMS) or bool(MONTHLY_PAYMENT_PATTERN.search(text))
    if tuition and living:
        return "verified_full", [_evidence("Benefits explicitly cover tuition and living/stipend support.", url, source_type, "high")]
    if "accommodation" in text and not tuition:
        return "excluded", [_evidence("Benefits are limited to accommodation without verified tuition coverage.", url, source_type, "high")]
    if _has(text, CAPPED_AWARD_TERMS):
        return "excluded", [_evidence("Benefits describe a capped fixed amount without verified tuition plus living coverage.", url, source_type, "high")]
    if "fully funded" in text or "full funding" in text or "full scholarship" in text:
        return "unknown", [_evidence("Full-funding label is present, but tuition plus living coverage is not both verified.", url, source_type, "medium")]
    return "unknown", [_evidence("No comprehensive funding package was verified.", url, source_type, "low")]


def analyze_nationality(value: str, url: str, source_type: str) -> tuple[str, str, list[dict[str, str]]]:
    text, official = _norm(value), source_type.startswith("official_")
    if any(term in text for term in ("indian nationals only", "indian citizens only", "only indian nationals", "only indian citizens", "open to indian nationals", "only for indian nationals", "open to indian citizens", "open to all indian citizens", "only eu nationals", "eu nationals only", "only eu citizens", "eu citizens only", "australian citizens only", "canadian citizens only")):
        return "excluded", "high", [_evidence("Nationality rule excludes a Beninese citizen.", url, source_type, "high")]
    if "benin" in text or "beninese" in text:
        return "eligible", "high", [_evidence("The eligible-country rule explicitly includes Benin.", url, source_type, "high")]
    if re.search(r"\b(?:eligible countries|eligible-country list|countries eligible)\b", text) and "," in text:
        return "excluded", "high", [_evidence("An explicit eligible-country list is present and does not include Benin.", url, source_type, "high")]
    if any(term in text for term in ("all countries", "all nationalities", "any nationality", "open to all nationals", "all over the world", "students worldwide", "open worldwide")):
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Eligibility rule is open to applicants from all countries/nationalities.", url, source_type, confidence)]
    if "all international students" in text:
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Rule explicitly covers all international students.", url, source_type, confidence)]
    if any(term in text for term in ("african nationals", "african countries", "sub-saharan african", "sub-saharan africa", "non-eu nationals", "non-eu applicants", "non-eea", "outside the eea")):
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Broad regional/development eligibility potentially covers a Beninese citizen; programme definition should be retained.", url, source_type, confidence)]
    if re.search(r"outside the eu(\/eea)?\b", text) or "non-eu/eea" in text or re.search(r"domicil\w* of origin outside", text):
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Eligibility is defined as domicile outside the EU/EEA area, which covers a Beninese citizen.", url, source_type, confidence)]
    if any(term in text for term in ("developing countries", "least developed countries")):
        return "eligible", "medium", [_evidence("Development-country eligibility may cover Benin, but the programme's country definition was not verified.", url, source_type, "medium")]
    if "international students" in text:
        return "unknown", "medium", [_evidence("International-student wording does not state whether all nationalities are eligible.", url, source_type, "medium")]
    return "unknown", "low", [_evidence("Nationality eligibility for Benin was not stated.", url, source_type, "low")]


def analyze_destination(destination: str, url: str, source_type: str) -> tuple[str, list[dict[str, str]]]:
    value = _text(destination)
    if not value:
        return "unknown", [_evidence("No structured institution or destination field was available.", url, source_type, "low")]
    normalized = _norm(value)
    if normalized in TARGET_COUNTRIES:
        return "eligible", [_evidence(f"Structured destination is {value}, a target country.", url, source_type, "high")]
    if normalized in {"usa", "united states", "united states of america", "india"}:
        return "excluded", [_evidence(f"Structured destination is {value}, outside the target-country list.", url, source_type, "high")]
    for country in TARGET_COUNTRIES:
        if re.search(rf"\b{re.escape(country)}\b", normalized):
            return "eligible", [_evidence(f"Structured destination field identifies {country.title()}, a target country.", url, source_type, "high")]
    if re.search(r"\b(?:usa|united states(?: of america)?|india)\b", normalized):
        return "excluded", [_evidence("Structured destination field identifies an excluded destination.", url, source_type, "high")]
    return "unknown", [_evidence("Structured destination names an institution or location but not a verifiable country.", url, source_type, "low")]


def analyze_application_location(value: str, url: str, source_type: str) -> tuple[str, list[dict[str, str]]]:
    text = _norm(value)
    restricted = ("must already reside", "must be resident", "currently reside", "residents only", "currently living", "currently studying", "already enrolled", "current students only", "local residence permit", "onshore applicants")
    if _has(text, restricted):
        return "excluded", [_evidence("Rules require the applicant to already live, study, or be enrolled at the destination.", url, source_type, "high")]
    if any(term in text for term in ("apply from abroad", "international applicants", "all international students", "international students may apply", "applications from outside")):
        return "eligible", [_evidence("Rules explicitly allow international applicants applying from abroad.", url, source_type, "high")]
    return "unknown", [_evidence("Application-from-abroad eligibility was not stated.", url, source_type, "low")]


def analyze_residence(eligible_country_text: str, url: str, source_type: str, residence_country: str = "India") -> tuple[str, list[dict[str, str]]]:
    """Decide whether the applicant's country of residence satisfies a closed
    eligible-country residence rule.

    Adapters pass ONLY the extracted residence/eligible-country list text, never
    free page text, so a stray mention of India elsewhere cannot qualify here.
    Nationality and residence stay separate: this says nothing about Beninese
    citizenship.
    """
    text = _norm(eligible_country_text)
    home = _norm(residence_country)
    if not text:
        return "unknown", [_evidence("No residence eligibility rule was stated.", url, source_type, "low")]
    if home and home in text:
        return "eligible", [_evidence(f"The residence rule explicitly includes {residence_country}.", url, source_type, "high")]
    closed = "," in text or re.search(r"\beligible countr\w*\b", text) or len(re.findall(r"\band\b", text)) >= 2
    if closed:
        return "excluded", [_evidence(f"The residence rule is a closed country list that does not include {residence_country}.", url, source_type, "high")]
    return "unknown", [_evidence("Residence eligibility could not be determined from the stated rule.", url, source_type, "medium")]


# Hard applicant requirements the fixed student profile cannot prove (the
# profile has no work-history, leadership-record, or language-test data).
# A matched pattern means the record can never be a guaranteed strong match,
# no matter how good the other evidence is.
REQUIREMENT_GAP_PATTERNS = (
    ("work_experience", re.compile(r"at least two years[’']? work experience|two years[’']? work experience|\b2,?800 hours\b|years of work experience (is |are )?required|minimum .*work experience", re.I)),
    ("leadership_record", re.compile(r"leadership (experience|qualities|record|potential).{0,60}required|demonstrated leadership.{0,40}required", re.I)),
)


def detect_requirement_gaps(requirement_text: str) -> list[str]:
    """Return requirement keys (e.g. work_experience) the profile cannot prove.

    Only explicit mandatory requirements count; mere preferences ("preference
    will be given to candidates employed in...") do not create gaps.
    """
    text = _norm(requirement_text or "")
    if not text:
        return []
    return [key for key, pattern in REQUIREMENT_GAP_PATTERNS if pattern.search(text)]


def analyze_cgpa(value: str, url: str, source_type: str) -> tuple[str, list[dict[str, str]]]:
    """Retain the original CGPA safeguard when a structured requirement exists."""
    text = _norm(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return "unknown", []
    required = float(match.group(1)) / float(match.group(2))
    applicant = STUDENT_PROFILE["cgpa"] / STUDENT_PROFILE["cgpa_scale"]
    if applicant >= required:
        return "eligible", [_evidence(f"Applicant CGPA meets the structured minimum {match.group(0)}.", url, source_type, "high")]
    return "excluded", [_evidence(f"Applicant CGPA is below the structured minimum {match.group(0)}.", url, source_type, "high")]


def analyze_deadline(value: str, url: str, source_type: str, today: date | None = None) -> tuple[str, list[str], list[dict[str, str]]]:
    raw = _text(value)
    if not raw:
        return "unknown", [], [_evidence("No deadline was found.", url, source_type, "low")]
    today, parsed = today or date.today(), []
    pattern = r"(?:\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*,?\s*\d{4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s*\d{4})"
    for candidate in re.findall(pattern, raw, re.I):
        for fmt in ("%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y"):
            try:
                parsed.append(datetime.strptime(candidate.replace(",", ""), fmt).date())
                break
            except ValueError:
                continue
    if not parsed:
        return "unknown", [raw], [_evidence("Deadline text could not be parsed reliably.", url, source_type, "medium")]
    future = [item for item in parsed if item >= today]
    if future:
        nearest = min(future).isoformat()
        return ("active" if min(future) == today else "upcoming"), [nearest], [_evidence(f"Relevant upcoming deadline is {nearest}.", url, source_type, "high")]
    return "expired", [item.isoformat() for item in parsed], [_evidence("All detected deadlines have passed.", url, source_type, "high")]


def evaluate_scholarship(*, title: str, url: str, source_type: str, degree: str = "", field: str = "", funding: str = "", nationality: str = "", destination: str = "", application_location: str = "", deadline: str = "", cgpa_requirements: str = "", verification_status: str = "unverified", today: date | None = None, residence_countries: str = "", requirement_text: str = "") -> dict[str, Any]:
    degree_match, degree_evidence = analyze_degree(degree, url, source_type)
    field_match, field_evidence = analyze_field(field, url, source_type)
    funding_status, funding_evidence = analyze_funding(funding, url, source_type)
    nationality_match, nationality_confidence, nationality_evidence = analyze_nationality(nationality, url, source_type)
    destination_match, destination_evidence = analyze_destination(destination, url, source_type)
    application_from_abroad, application_location_evidence = analyze_application_location(application_location, url, source_type)
    residence_match, residence_evidence = analyze_residence(residence_countries, url, source_type)
    cgpa_match, cgpa_evidence = analyze_cgpa(cgpa_requirements, url, source_type)
    deadline_state, deadlines, deadline_evidence = analyze_deadline(deadline, url, source_type, today)
    profile_requirements_missing = detect_requirement_gaps(requirement_text)
    outcomes = (degree_match, field_match, funding_status, nationality_match, destination_match, application_from_abroad, residence_match, deadline_state)
    rejected = any(item == "excluded" for item in outcomes) or cgpa_match == "excluded" or deadline_state == "expired"
    passed = degree_match == "eligible" and field_match == "eligible" and funding_status == "verified_full" and nationality_match == "eligible" and nationality_confidence == "high" and destination_match == "eligible" and application_from_abroad == "eligible" and residence_match != "excluded" and cgpa_match != "excluded" and deadline_state in {"active", "upcoming"} and verification_status == "verified" and not profile_requirements_missing
    match_status = "strong_match" if passed else ("rejected" if rejected else "possible_match")
    evidence = degree_evidence + field_evidence + funding_evidence + nationality_evidence + destination_evidence + application_location_evidence + residence_evidence + cgpa_evidence + deadline_evidence
    gap_warnings = [f"Unverified applicant requirement: {gap}." for gap in profile_requirements_missing]
    return {"degree_match": degree_match, "degree_evidence": degree_evidence, "field_match": field_match, "field_evidence": field_evidence, "funding_status": funding_status, "funding_evidence": funding_evidence, "nationality_match": nationality_match, "nationality_confidence": nationality_confidence, "nationality_evidence": nationality_evidence, "destination": destination, "destination_match": destination_match, "destination_evidence": destination_evidence, "application_from_abroad": application_from_abroad, "application_location_evidence": application_location_evidence, "residence_match": residence_match, "residence_evidence": residence_evidence, "cgpa_match": cgpa_match, "cgpa_evidence": cgpa_evidence, "deadline_state": deadline_state, "deadlines": deadlines, "deadline_evidence": deadline_evidence, "verification_status": verification_status, "match_status": match_status, "match_score": 100 if match_status == "strong_match" else 0, "recommendation": "include" if match_status == "strong_match" else "exclude", "reasons": [item["claim"] for item in evidence], "warnings": [item["claim"] for item in evidence if item["confidence"] != "high"] + gap_warnings, "profile_requirements_missing": profile_requirements_missing, "profile_version": "evidence-v3", "profile_rule": "Master's only; verified tuition plus living funding; Benin eligibility; target destination; apply from India; active deadline; official verification"}


def strict_match(**kwargs: Any) -> dict[str, Any]:
    """Compatibility wrapper for existing callers while using the v3 engine."""
    return evaluate_scholarship(title=kwargs.get("title", ""), url=kwargs.get("url", ""), source_type=kwargs.get("source_type", "unknown"), degree=kwargs.get("degree", ""), field=kwargs.get("courses", ""), funding=kwargs.get("funding", ""), nationality=kwargs.get("nationality", ""), destination=kwargs.get("destination", ""), application_location=kwargs.get("page_text", ""), deadline=kwargs.get("deadline", ""), cgpa_requirements=" ".join(kwargs.get("cgpa_requirements", [])), verification_status=kwargs.get("verification_status", "unverified"), residence_countries=kwargs.get("residence_countries", ""), requirement_text=kwargs.get("requirement_text", ""))
