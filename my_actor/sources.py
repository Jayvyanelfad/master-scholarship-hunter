"""Source registry for Master Scholarship Hunter.

The registry is derived from real source adapters
(``my_actor.source_adapters``): a source appears here if and only if an
adapter object describes it. Nothing is listed as supported unless its
adapter actually parses discovery pages. Sources whose discovery URL could
not be verified stay ``enabled = False`` with a documented reason.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .source_adapters import build_adapters
from .source_adapters.base import SourceAdapter, host_in_domains


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
    # Extended multi-source metadata (all derived from the live adapter).
    discovery_supported: bool = False
    verification_supported: bool = False
    status: str = "disabled"
    status_reason: str = ""
    destination: str = ""
    official_domains: tuple[str, ...] = ()


def _definition_from_adapter(adapter: SourceAdapter, priority: int) -> SourceDefinition:
    discovery_supported = bool(adapter.discovery_urls) and adapter.enabled
    return SourceDefinition(
        identifier=adapter.source_id,
        name=adapter.display_name,
        base_urls=adapter.discovery_urls,
        source_type=adapter.source_type,
        priority=priority,
        enabled=adapter.enabled,
        discovery_strategy=adapter.discovery_strategy,
        notes=adapter.notes or adapter.status_reason,
        discovery_supported=discovery_supported,
        verification_supported=adapter.enabled,
        status="enabled" if adapter.enabled else "disabled",
        status_reason=adapter.status_reason,
        destination=adapter.destination,
        official_domains=adapter.official_domains,
    )


def _build_registry() -> tuple[SourceDefinition, ...]:
    priorities = {
        "wemakescholars": 40,
        "erasmus_mundus": 100,
        "daad": 100,
        "vlir_uos": 95,
        "chevening": 100,
        "goi_ies": 95,
        "mext": 100,
        "mastercard_foundation": 95,
        "nl_scholarship": 60,
        "si_sweden": 90,
        "finland": 70,
        "norway": 70,
        "switzerland": 80,
        "austria": 80,
        "australia": 85,
    }
    return tuple(
        _definition_from_adapter(adapter, priorities.get(adapter.source_id, 50))
        for adapter in build_adapters()
    )


SOURCE_REGISTRY: tuple[SourceDefinition, ...] = _build_registry()


def get_adapter(source_id: str) -> SourceAdapter | None:
    for adapter in build_adapters():
        if adapter.source_id == (source_id or "").strip().lower():
            return adapter
    return None


def source_by_url(url: str) -> SourceDefinition | None:
    for source in SOURCE_REGISTRY:
        if host_in_domains(url, source.official_domains):
            return source
    return None


def configured_sources(source_ids: list[str] | None = None) -> list[SourceDefinition]:
    """Return production sources, or an explicit selection.

    ``None`` (or ``[]``) means the production default: every enabled source.
    ``["all"]`` selects every known source including disabled ones (disabled
    adapters still skip themselves at runtime with a logged reason).
    Otherwise only the named identifiers are returned.
    """
    if not source_ids:
        return [source for source in SOURCE_REGISTRY if source.enabled]
    selected = {item.strip().lower() for item in source_ids if item.strip()}
    if "all" in selected:
        return list(SOURCE_REGISTRY)
    return [source for source in SOURCE_REGISTRY if source.identifier in selected]


def enabled_source_ids() -> list[str]:
    return [source.identifier for source in SOURCE_REGISTRY if source.enabled]


def registry_as_dicts() -> list[dict[str, object]]:
    return [asdict(source) for source in SOURCE_REGISTRY]


def status_table() -> list[dict[str, str]]:
    """Exactly which sources are enabled/disabled and why (for logs/README)."""
    return [
        {
            "source_id": source.identifier,
            "name": source.name,
            "status": source.status,
            "discovery": "supported" if source.discovery_supported else "unsupported",
            "verification": "supported" if source.verification_supported else "unsupported",
            "reason": source.status_reason,
        }
        for source in SOURCE_REGISTRY
    ]
