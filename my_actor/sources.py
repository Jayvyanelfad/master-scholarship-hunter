"""Extensible discovery-source registry for Master Scholarship Hunter.

Each source has an explicit discovery strategy.  The crawler currently has a
structured adapter for WeMakeScholars; official pages are deliberately not
forced through that parser because their markup and eligibility vocabulary
differ.  They can be enabled with direct URLs and source-specific adapters as
they are added.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceDefinition:
    identifier: str
    name: str
    base_urls: tuple[str, ...]
    source_type: str
    priority: int
    enabled: bool
    discovery_strategy: str
    notes: str


SOURCE_REGISTRY: tuple[SourceDefinition, ...] = (
    SourceDefinition("wemakescholars", "WeMakeScholars", ("https://www.wemakescholars.com/Masters-scholarships-in-computer-sciences-and-information-technology-to-study-abroad",), "reputable_aggregator", 40, True, "listing_then_detail", "Discovery source; strong matches require official evidence."),
    SourceDefinition("erasmus_mundus", "Erasmus Mundus", ("https://erasmus-plus.ec.europa.eu/",), "official_program", 100, False, "source_specific_adapter", "EU master's joint-programme scholarships."),
    SourceDefinition("daad", "DAAD", ("https://www.daad.de/en/",), "official_government", 100, False, "source_specific_adapter", "German Academic Exchange Service."),
    SourceDefinition("chevening", "Chevening", ("https://www.chevening.org/",), "official_government", 100, False, "source_specific_adapter", "UK government scholarship programme."),
    SourceDefinition("commonwealth", "Commonwealth Scholarships", ("https://cscuk.fcdo.gov.uk/",), "official_government", 100, False, "source_specific_adapter", "UK Commonwealth Scholarship Commission."),
    SourceDefinition("swedish_institute", "Swedish Institute", ("https://si.se/en/",), "official_government", 100, False, "source_specific_adapter", "Swedish Institute scholarships."),
    SourceDefinition("vlir_uos", "VLIR-UOS", ("https://www.vliruos.be/en",), "official_program", 95, False, "source_specific_adapter", "Belgian development cooperation scholarships."),
    SourceDefinition("ares", "ARES", ("https://www.ares-ac.be/",), "official_program", 95, False, "source_specific_adapter", "Belgian development cooperation scholarships."),
    SourceDefinition("ireland", "Government of Ireland", ("https://hea.ie/",), "official_government", 95, False, "source_specific_adapter", "Government of Ireland international education awards."),
    SourceDefinition("mext", "MEXT", ("https://www.mext.go.jp/en/",), "official_government", 100, False, "source_specific_adapter", "Japanese Government scholarship programme."),
    SourceDefinition("mastercard_foundation", "Mastercard Foundation Scholars Program", ("https://mastercardfdn.org/",), "official_program", 95, False, "source_specific_adapter", "Partner-university programme for African students."),
)


def source_by_url(url: str) -> SourceDefinition | None:
    hostname = (urlparse(url).hostname or "").lower()
    for source in SOURCE_REGISTRY:
        domains = {(urlparse(base).hostname or "").lower() for base in source.base_urls}
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains):
            return source
    return None


def configured_sources(source_ids: list[str] | None = None) -> list[SourceDefinition]:
    selected = {item.strip().lower() for item in source_ids or [] if item.strip()}
    return [source for source in SOURCE_REGISTRY if source.enabled or source.identifier in selected]


def registry_as_dicts() -> list[dict[str, object]]:
    return [asdict(source) for source in SOURCE_REGISTRY]
