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
    partial = ("tuition only", "tuition waiver only", "tuition discount", "partial tuition", "partial funding", "bursary", "accommodation only", "meal allowance", "small grant")
    if _has(text, partial) or re.search(r"\b(?:25|50|75)%\b", text):
        return "excluded", [_evidence("Benefits are explicitly partial or limited to one expense.", url, source_type, "high")]
    tuition = any(term in text for term in ("tuition fees", "tuition fee", "full tuition", "covers tuition", "tuition coverage"))
    living = any(term in text for term in ("living expenses", "living allowance", "monthly stipend", "monthly allowance", "maintenance allowance", "maintenance stipend", "cost of living", "stipend"))
    if tuition and living:
        return "verified_full", [_evidence("Benefits explicitly cover tuition and living/stipend support.", url, source_type, "high")]
    if "fully funded" in text or "full funding" in text or "full scholarship" in text:
        return "unknown", [_evidence("Full-funding label is present, but tuition plus living coverage is not both verified.", url, source_type, "medium")]
    return "unknown", [_evidence("No comprehensive funding package was verified.", url, source_type, "low")]


def analyze_nationality(value: str, url: str, source_type: str) -> tuple[str, str, list[dict[str, str]]]:
    text, official = _norm(value), source_type.startswith("official_")
    if any(term in text for term in ("indian nationals only", "indian citizens only", "only indian nationals", "only indian citizens", "only eu nationals", "eu nationals only", "only eu citizens", "eu citizens only", "australian citizens only", "canadian citizens only")):
        return "excluded", "high", [_evidence("Nationality rule excludes a Beninese citizen.", url, source_type, "high")]
    if "benin" in text or "beninese" in text:
        return "eligible", "high", [_evidence("The eligible-country rule explicitly includes Benin.", url, source_type, "high")]
    if re.search(r"\b(?:eligible countries|eligible-country list|countries eligible)\b", text) and "," in text:
        return "excluded", "high", [_evidence("An explicit eligible-country list is present and does not include Benin.", url, source_type, "high")]
    if any(term in text for term in ("all countries", "all nationalities", "any nationality", "open to all nationals")):
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Eligibility rule is open to applicants from all countries/nationalities.", url, source_type, confidence)]
    if "all international students" in text:
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Rule explicitly covers all international students.", url, source_type, confidence)]
    if any(term in text for term in ("african nationals", "sub-saharan african", "non-eu nationals")):
        confidence = "high" if official else "medium"
        return "eligible", confidence, [_evidence("Broad regional/development eligibility potentially covers a Beninese citizen; programme definition should be retained.", url, source_type, confidence)]
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


def evaluate_scholarship(*, title: str, url: str, source_type: str, degree: str = "", field: str = "", funding: str = "", nationality: str = "", destination: str = "", application_location: str = "", deadline: str = "", cgpa_requirements: str = "", verification_status: str = "unverified", today: date | None = None) -> dict[str, Any]:
    degree_match, degree_evidence = analyze_degree(degree, url, source_type)
    field_match, field_evidence = analyze_field(field, url, source_type)
    funding_status, funding_evidence = analyze_funding(funding, url, source_type)
    nationality_match, nationality_confidence, nationality_evidence = analyze_nationality(nationality, url, source_type)
    destination_match, destination_evidence = analyze_destination(destination, url, source_type)
    application_from_abroad, application_location_evidence = analyze_application_location(application_location, url, source_type)
    cgpa_match, cgpa_evidence = analyze_cgpa(cgpa_requirements, url, source_type)
    deadline_state, deadlines, deadline_evidence = analyze_deadline(deadline, url, source_type, today)
    outcomes = (degree_match, field_match, funding_status, nationality_match, destination_match, application_from_abroad, deadline_state)
    rejected = any(item == "excluded" for item in outcomes) or cgpa_match == "excluded" or deadline_state == "expired"
    passed = degree_match == "eligible" and field_match == "eligible" and funding_status == "verified_full" and nationality_match == "eligible" and nationality_confidence == "high" and destination_match == "eligible" and application_from_abroad == "eligible" and cgpa_match != "excluded" and deadline_state in {"active", "upcoming"} and verification_status == "verified"
    match_status = "strong_match" if passed else ("rejected" if rejected else "possible_match")
    evidence = degree_evidence + field_evidence + funding_evidence + nationality_evidence + destination_evidence + application_location_evidence + cgpa_evidence + deadline_evidence
    return {"degree_match": degree_match, "degree_evidence": degree_evidence, "field_match": field_match, "field_evidence": field_evidence, "funding_status": funding_status, "funding_evidence": funding_evidence, "nationality_match": nationality_match, "nationality_confidence": nationality_confidence, "nationality_evidence": nationality_evidence, "destination": destination, "destination_match": destination_match, "destination_evidence": destination_evidence, "application_from_abroad": application_from_abroad, "application_location_evidence": application_location_evidence, "cgpa_match": cgpa_match, "cgpa_evidence": cgpa_evidence, "deadline_state": deadline_state, "deadlines": deadlines, "deadline_evidence": deadline_evidence, "verification_status": verification_status, "match_status": match_status, "match_score": 100 if match_status == "strong_match" else 0, "recommendation": "include" if match_status == "strong_match" else "exclude", "reasons": [item["claim"] for item in evidence], "warnings": [item["claim"] for item in evidence if item["confidence"] != "high"], "profile_version": "evidence-v3", "profile_rule": "Master's only; verified tuition plus living funding; Benin eligibility; target destination; apply from India; active deadline; official verification"}


def strict_match(**kwargs: Any) -> dict[str, Any]:
    """Compatibility wrapper for existing callers while using the v3 engine."""
    return evaluate_scholarship(title=kwargs.get("title", ""), url=kwargs.get("url", ""), source_type=kwargs.get("source_type", "unknown"), degree=kwargs.get("degree", ""), field=kwargs.get("courses", ""), funding=kwargs.get("funding", ""), nationality=kwargs.get("nationality", ""), destination=kwargs.get("destination", ""), application_location=kwargs.get("page_text", ""), deadline=kwargs.get("deadline", ""), cgpa_requirements=" ".join(kwargs.get("cgpa_requirements", [])), verification_status=kwargs.get("verification_status", "unverified"))
