"""Safe official-link selection and evidence merging for discovery records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
# Query keys that only select a language variant of the same page.
LOCALE_QUERY_KEYS = {"locale", "lang", "language", "setlang", "clang"}
# First path segments that only select a language variant of the same page.
LOCALE_PATH_SEGMENTS = {
    "en", "fr", "de", "es", "nl", "it", "pt", "sv", "fi", "da", "no", "nb",
    "ja", "zh", "ar", "sw", "eng", "fre", "ger",
}
SOCIAL_OR_TRACKING_DOMAINS = (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "whatsapp.com", "bit.ly", "tinyurl.com",
)
OFFICIAL_LINK_TERMS = (
    "official website", "scholarship website", "official scholarship", "apply now",
    "apply online", "application portal", "apply", "programme page", "program page",
    "admissions page", "admission", "university website",
)
FIELD_LABELS = {
    "degree": ("Eligible Degrees", "Degree", "Degree level"),
    "field": ("Eligible Courses", "Eligible Programs", "Eligible Programmes", "Field of study"),
    "funding": ("Scholarship Amount", "Scholarship Coverage", "Which costs are covered", "Funding Type", "Funding", "Benefits", "Financial coverage"),
    "nationality": ("Eligible Nationalities", "Eligible countries", "Nationality", "Who can apply"),
    "destination": ("Scholarship can be taken at", "Can Be Taken At", "Can be taken at", "Study At", "Study at", "Destination", "Country of study"),
    "deadline": ("Deadline", "Application deadline", "Closing date"),
    "cgpa": ("Minimum CGPA", "Minimum GPA", "CGPA requirement", "GPA requirement"),
    "provider": ("Provider", "Scholarship provider"),
    "application_location": ("Application location", "Residency requirement", "Applicant requirements", "Eligibility criteria"),
}

# Currency words mapped to codes so prose such as "1,400 euros per month"
# uses the same vocabulary as symbol/code amounts. Meaning-preserving
# canonicalization only; amounts and periods are never altered or invented.
CURRENCY_WORDS = {
    "euros": "EUR", "euro": "EUR", "dollars": "USD", "dollar": "USD",
    "yen": "JPY", "pounds": "GBP", "pound": "GBP", "francs": "CHF",
    "franc": "CHF", "krona": "SEK",
}
_CURRENCY_WORD_PATTERN = re.compile(
    r"\b(euros?|dollars?|yen|pounds?|francs?|krona)\b", re.I
)
# Amount-first prose ("1,400 euros per month") reordered to code-first
# ("EUR 1,400 per month") so monthly-support evidence uses one vocabulary.
_AMOUNT_FIRST_PATTERN = re.compile(
    r"([\d][\d,.\s]*(?:\s*[~\u2013\u2014\-–]|to\s+)?\s*[\d][\d,.]*)\s+(euros?|dollars?|yen|pounds?|francs?|krona)\b",
    re.I,
)


def normalize_funding_prose(value: str) -> str:
    """Canonicalize currency words to codes inside funding evidence text."""
    if not value:
        return value

    def reorder(match: re.Match) -> str:
        code = CURRENCY_WORDS.get(match.group(2).lower(), match.group(2))
        return f"{code} {match.group(1).strip()}"

    value = _AMOUNT_FIRST_PATTERN.sub(reorder, value)

    def replace(match: re.Match) -> str:
        return CURRENCY_WORDS.get(match.group(1).lower(), match.group(1))

    return _CURRENCY_WORD_PATTERN.sub(replace, value)


@dataclass(frozen=True)
class LinkCandidate:
    href: str
    text: str


def canonical_url(url: str) -> str:
    """Normalize identity URLs: tracking and language markers removed.

    Language variants (``/es/...`` vs ``/...?locale=es``) collapse to one
    identity so localized duplicates deduplicate instead of multiplying.
    """
    parsed = urlparse(url)
    query = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and key.lower() not in LOCALE_QUERY_KEYS
        and not key.lower().startswith("utm_")
    ]
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[0].lower() in LOCALE_PATH_SEGMENTS and len(segments) > 1:
        segments = segments[1:]
    path = ("/" + "/".join(segments)).rstrip("/") or "/"
    # Preserve the empty-path vs root distinction used by older keys.
    if not segments:
        path = parsed.path.rstrip("/")
    return urlunparse((
        parsed.scheme.lower(), parsed.netloc.lower(), path, "",
        urlencode(query, doseq=True), "",
    ))


def _is_external_non_social(url: str, discovery_url: str) -> bool:
    parsed, discovery = urlparse(url), urlparse(discovery_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host or host == (discovery.hostname or "").lower():
        return False
    return not any(host == domain or host.endswith(f".{domain}") for domain in SOCIAL_OR_TRACKING_DOMAINS)


def is_acceptable_official_link(url: str, discovery_url: str) -> bool:
    """Public gate for adapter follow-up links: external, non-social only.

    Adapters additionally constrain accepted hosts to their official domains
    or explicitly linked programme/application pages; this shared check
    guarantees social, tracking, and same-page links never pass.
    """
    return _is_external_non_social(url, discovery_url)


def _score_candidate(candidate: LinkCandidate, provider: str) -> int:
    text = re.sub(r"\s+", " ", candidate.text).strip().lower()
    score = 0
    for index, term in enumerate(OFFICIAL_LINK_TERMS):
        if term in text:
            score = max(score, 100 - index)
    if not score:
        return 0
    provider_terms = [term for term in re.findall(r"[a-z0-9]{4,}", provider.lower()) if term not in {"university", "scholarship"}]
    host = (urlparse(candidate.href).hostname or "").lower()
    if provider_terms and any(term in host for term in provider_terms):
        score += 10
    return score


def select_official_url(discovery_url: str, provider: str, candidates: list[LinkCandidate]) -> str | None:
    """Return one explicit official/application candidate, never a random outbound URL."""
    ranked: list[tuple[int, str]] = []
    for candidate in candidates:
        absolute = urljoin(discovery_url, candidate.href)
        if not _is_external_non_social(absolute, discovery_url):
            continue
        score = _score_candidate(LinkCandidate(absolute, candidate.text), provider)
        if score:
            ranked.append((score, canonical_url(absolute)))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def official_source_type(url: str) -> str:
    path, host = urlparse(url).path.lower(), (urlparse(url).hostname or "").lower()
    if path.endswith(".pdf"):
        return "official_document"
    if host.endswith(".gov") or ".gov." in host:
        return "official_government"
    if host.endswith(".edu") or ".ac." in host:
        return "official_university"
    return "official_program"


def extract_structured_fields(text: str) -> dict[str, str]:
    """Extract only labelled source fields from flattened page text."""
    text = re.sub(r"\s+", " ", text).strip()
    # A boundary keyword only terminates a value when it behaves like a new
    # label (the keyword plus at most two words, then a colon) or at the end
    # of the text. This prevents in-value phrases such as "eligible for
    # admission" or "Africans from eligible countries" from cutting evidence.
    boundaries = r"(?=\s+(?:Eligible|Eligibility|Funding|Deadline|Application|Provider|Scholarship can be taken|Can be taken|Study at|Overview|Details|Benefits|Requirements|Country of study|Minimum|Degree|Field of study|Residency)(?:\s+[A-Za-z]+){0,2}\s*:|\s*$)"
    fields: dict[str, str] = {}
    for name, labels in FIELD_LABELS.items():
        fields[name] = ""
        for label in labels:
            match = re.search(rf"\b{re.escape(label)}\b\s*[:\-]?\s*(.{{1,600}}?){boundaries}", text, re.I)
            if match:
                fields[name] = re.sub(r"\s+", " ", match.group(1)).strip()
                break
    fields["funding"] = normalize_funding_prose(fields["funding"])
    return fields


def merge_fields(discovery_fields: dict[str, str], official_fields: dict[str, str]) -> dict[str, str]:
    """Official non-empty values override discovery values for display and auditing."""
    return {
        key: official_fields.get(key, "").strip() or discovery_fields.get(key, "").strip()
        for key in set(discovery_fields) | set(official_fields)
    }
