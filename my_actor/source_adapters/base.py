"""Expandable source-adapter framework for Master Scholarship Hunter.

Every discovery source is described by a small adapter object. An adapter
parses listing pages into candidate detail URLs and detail pages into shared
evidence fields. Adapters use only the standard library so their parsing can
be unit-tested without Apify, Crawlee, or network access.

Design rules for every adapter:

- Never invent facts. Only extract what the fetched page states.
- Never treat a discovery/listing page as the scholarship itself.
- Only same-organisation official domains (``official_domains``) or pages
  explicitly linked as the official programme/application page from a
  recognized source may become official evidence.
- Social, tracking, search-result, and unrelated outbound links are never
  official evidence (enforced in ``my_actor.verification``).
- Nationality (citizenship) and residence (where the applicant lives) are
  separate fields. "Studying in India" must never become "Indian national".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


SHARED_FIELD_KEYS = (
    "degree", "field", "funding", "nationality", "destination",
    "deadline", "cgpa", "provider", "application_location",
)


def blank_fields() -> dict[str, str]:
    """Shared evidence-field dict every adapter fills from page content."""
    return {key: "" for key in SHARED_FIELD_KEYS}


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href", "") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = re.sub(r"\s+", " ", "".join(self._text)).strip()
            self.links.append((self._href, text))
            self._href = ""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def extract_links(html: str) -> list[tuple[str, str]]:
    """Return ``(href, anchor_text)`` pairs in document order."""
    parser = _LinkExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    return parser.links


def extract_text(html: str) -> str:
    """Return flattened visible page text with collapsed whitespace."""
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def extract_title(html: str) -> str:
    """Return the first ``h1`` text, falling back to ``<title>``."""

    class TitleParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.h1: list[str] = []
            self.title: list[str] = []
            self._active: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in {"h1", "title"} and self._active is None:
                self._active = tag

        def handle_data(self, data: str) -> None:
            if self._active == "h1":
                self.h1.append(data)
            elif self._active == "title":
                self.title.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag == self._active:
                self._active = None

    parser = TitleParser()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    heading = re.sub(r"\s+", " ", "".join(parser.h1)).strip()
    if heading:
        return heading
    return re.sub(r"\s+", " ", "".join(parser.title)).strip()


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


# Anchor-text signals of site navigation, never of a scholarship record.
# Applied by adapters when qualifying listing links. Deliberately narrow:
# generic calls-to-action such as "read more" are NOT listed because real
# programme links use them.
NAV_ANCHOR_STOPLIST = (
    "admissions", "cost of living", "cost and requirements", "fees and cost", "fees & cost",
    "universities", "university list", "student stories", "plan your stay",
    "after your studies", "all programmes", "all programs",
    "find a programme", "find your programme", "find a program",
    "search results", "view all", "see all", "bachelor", "doctoral", "phd",
    "exchange", "contact us", "about us", "more resources",
)


def matches_nav_anchor(anchor: str) -> bool:
    lowered = re.sub(r"\s+", " ", anchor or "").strip().lower()
    return any(token in lowered for token in NAV_ANCHOR_STOPLIST)


# Domain vocabulary proving an extracted field carries real evidence rather
# than a label-echo artifact (for example "Funding" matched inside the
# heading "Funding your studies").
EVIDENCE_VOCAB = {
    "degree": ("master", "phd", "bachelor", "doctor", "postgrad", "graduate", "diploma", "degree"),
    "funding": ("tuition", "stipend", "living", "allowance", "grant", "award", "fund", "fee", "waiver", "scholarship", "cover", "month", "travel", "insurance", "accommodation", "eur", "usd", "jpy", "gbp", "chf", "\u20ac", "$", "\u00a3", "\u00a5"),
    "nationality": ("benin", "countr", "nation", "citizen", "eligib", "international", "africa", "europe", "eea", "worldwide", "domicil", "resident", "applicant"),
    "deadline": ("deadline", "january", "february", "march", "april", "june", "july", "august", "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "202", "203"),
}


def field_has_substance(field_name: str, value: str) -> bool:
    text = re.sub(r"\s+", " ", value or "").strip().lower()
    if not text:
        return False
    return any(term in text for term in EVIDENCE_VOCAB.get(field_name, ()))


def is_generic_info_page(title: str, fields: dict[str, str]) -> str:
    """Return a reason when a page is generic info rather than a record.

    A page may only become a scholarship record when it either names an
    award/programme in its title or carries at least one structured evidence
    field (degree, funding, nationality, or deadline). Informational shells
    ("Funding your studies", "Study opportunities", "Finding
    Scholarships") provide no record identity and must not become records;
    they can still serve as listing pages that link to real records.
    """
    text = re.sub(r"\s+", " ", title or "").strip().lower()
    substantive = any(
        field_has_substance(key, fields.get(key, ""))
        for key in ("degree", "funding", "nationality", "deadline")
    )
    if substantive:
        return ""
    if not text:
        return "Non-record page (no title and no evidence)."
    return f"Non-record informational page ({text[:80]})."


def canonical_programme_url(url: str) -> str:
    """Identity URL with language variants collapsed (delegates to verification)."""
    from ..verification import canonical_url

    return canonical_url(url)


# Page shapes that are never scholarship records, whatever the source.
JUNK_TITLE_PATTERNS = (
    "cookie consent", "cookie settings", "cookie policy", "cookies policy",
    "page not found", "404", "access denied", "forbidden", "error 403",
    "select your language", "choose your language", "select language",
    "service unavailable", "under maintenance", "just a moment",
)
JUNK_PATH_PATTERNS = (
    "cookie", "cookies", "/faq", "faq-", "accessibility", "barrierefreiheit",
    "imprint", "impressum", "datenschutz", "privacy", "/news", "/presse",
    "/press", "/events", "/contact", "/sitemap", "/search", "language-selector",
)


def is_junk_page(html: str, url: str) -> str:
    """Return a reason when a fetched page is not a content page, else "".

    Conservative by design: a page is junk only on an explicit signal
    (junk title, or a junk path with almost no readable text). Real
    scholarship pages are never skipped by this check.
    """
    title = extract_title(html).lower()
    for pattern in JUNK_TITLE_PATTERNS:
        if pattern and pattern in title:
            return f"Non-record page (title indicates '{pattern}')."
    lowered_url = (url or "").lower()
    if any(pattern in lowered_url for pattern in JUNK_PATH_PATTERNS):
        if len(extract_text(html)) < 1500:
            return "Non-record navigation/utility page."
    return ""


def extract_evidence_sentences(text: str, keywords: tuple[str, ...], max_chars: int = 600) -> str:
    """Join source sentences containing any keyword (fallback evidence).

    Used only when no labelled field was extracted, so programme prose
    ("covers tuition fees and a monthly stipend") still becomes evidence
    instead of an empty field. Never invents content: sentences come
    verbatim from the fetched page.
    """
    lowered_keywords = [keyword.lower() for keyword in keywords]
    picked: list[str] = []
    total = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        if len(cleaned) < 20 or len(cleaned) > 400:
            continue
        lowered = cleaned.lower()
        if any(keyword in lowered for keyword in lowered_keywords):
            picked.append(cleaned)
            total += len(cleaned)
            if total >= max_chars:
                break
    return " ".join(picked)


def host_in_domains(url: str, domains: tuple[str, ...]) -> bool:
    host = hostname(url)
    wanted = {domain.lower().lstrip(".") for domain in domains}
    return any(host == domain or host.endswith(f".{domain}") for domain in wanted)


def absolutize(base_url: str, href: str) -> str:
    return urljoin(base_url, href or "")


@dataclass(frozen=True)
class DiscoveryCandidate:
    """One candidate detail page found on a listing page."""

    url: str
    title: str = ""
    context: str = ""


@dataclass(frozen=True)
class DetailResult:
    """Evidence extracted from one detail page.

    ``fields`` uses the shared evidence keys. ``residence_countries`` holds
    ONLY an extracted eligible-country residence list (never free page text).
    ``requirement_text`` holds ONLY mandatory applicant-requirement sentences
    (work experience, leadership) used for profile-requirement gap detection.
    ``follow_links`` holds deeper official pages (partner-university model).
    ``is_hop`` marks index/catalogue pages that only resolve deeper official
    pages: routes enqueue the follow-ups without storing a stub record.
    ``skip`` marks non-record pages (language selectors, cookie walls,
    navigation shells): routes store nothing for them at all.
    """

    title: str
    fields: dict[str, str]
    residence_countries: str = ""
    requirement_text: str = ""
    follow_links: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    is_hop: bool = False
    skip: bool = False
    skip_reason: str = ""


@dataclass(frozen=True)
class ListingResult:
    candidates: tuple[DiscoveryCandidate, ...] = ()
    next_page_url: str | None = None


@dataclass
class SourceAdapter:
    """Base class for one discovery source.

    Subclasses fill in the declarative attributes and the two parsers.
    ``detail_is_official`` marks sources whose own detail pages already are
    official evidence (DAAD, VLIR-UOS, Chevening, ...). Aggregators such as
    WeMakeScholars set it to ``False`` so a second official hop is required.
    """

    source_id: str = ""
    display_name: str = ""
    source_type: str = "official_program"
    discovery_urls: tuple[str, ...] = ()
    discovery_strategy: str = ""
    pagination: str = "none"
    max_pages: int = 5
    max_records: int = 50
    official_domains: tuple[str, ...] = ()
    destination: str = ""
    detail_is_official: bool = True
    enabled: bool = False
    status_reason: str = ""
    notes: str = ""

    def is_listing_url(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return host_in_domains(url, self.official_domains) and any(
            token in path for token in ("scholarship", "funding", "grant", "opportunit", "catalogue", "program", "finance")
        )

    def is_detail_url(self, url: str) -> bool:
        return False

    def parse_listing(self, html: str, base_url: str) -> ListingResult:
        return ListingResult()

    def parse_detail(self, html: str, url: str) -> DetailResult:
        return DetailResult(title=extract_title(html), fields=blank_fields())


def dedup_key(title: str, provider: str, destination: str, official_url: str = "", discovery_url: str = "") -> str:
    """Stable cross-source identity key.

    The canonical official URL wins when verification succeeded, so the same
    scholarship discovered via WeMakeScholars and DAAD collapses to one
    record. Otherwise identity falls back to normalized discovery evidence.
    """
    if official_url:
        return f"official|{official_url.strip().lower().rstrip('/')}"
    norm = lambda value: re.sub(r"\s+", " ", (value or "")).strip().lower()
    return "|".join(("discovery", norm(title), norm(provider), norm(destination), (discovery_url or "").strip().lower().rstrip("/")))
