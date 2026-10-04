"""Crawler-independent pipeline state: health, deduplicated store, diagnostics.

This module has no Apify/Crawlee imports so unit tests can cover source
failure isolation, cross-source deduplication, and zero-result diagnostics
without a browser or network. ``my_actor.routes`` wires these pieces into
the live crawl.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .source_adapters.base import SourceAdapter


@dataclass
class SourceHealth:
    """Per-source counters for one run (see task: source-level logging).

    ``verified`` counts records whose official evidence was merged
    (evidence-level verification). ``strong_matches`` counts records that
    additionally passed every strict eligibility gate. ``pages_seen``
    counts listing/detail pages processed; ``junk_skipped`` counts
    non-record pages discarded before they could become records.
    """

    source_id: str
    display_name: str = ""
    attempted: int = 0
    pages_seen: int = 0
    discovered: int = 0
    official_queued: int = 0
    official_fetched: int = 0
    verified: int = 0
    strong_matches: int = 0
    stored: int = 0
    junk_skipped: int = 0
    possible: int = 0
    rejected: int = 0
    errors: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "attempted": self.attempted,
            "pages_seen": self.pages_seen,
            "discovered": self.discovered,
            "official_queued": self.official_queued,
            "official_fetched": self.official_fetched,
            "verified": self.verified,
            "strong_matches": self.strong_matches,
            "stored": self.stored,
            "junk_skipped": self.junk_skipped,
            "possible": self.possible,
            "rejected": self.rejected,
            "errors": self.errors,
            "note": self.note,
        }


class HealthTracker:
    def __init__(self) -> None:
        self._health: dict[str, SourceHealth] = {}

    def record(self, source_id: str, display_name: str = "") -> SourceHealth:
        entry = self._health.get(source_id)
        if entry is None:
            entry = SourceHealth(source_id=source_id, display_name=display_name or source_id)
            self._health[source_id] = entry
        elif display_name and not entry.display_name:
            entry.display_name = display_name
        return entry

    def fail(self, source_id: str, display_name: str, note: str) -> SourceHealth:
        """Record an isolated source failure without affecting other sources."""
        entry = self.record(source_id, display_name)
        entry.errors += 1
        entry.note = note
        return entry

    def as_dicts(self) -> dict[str, dict[str, object]]:
        return {source_id: entry.as_dict() for source_id, entry in self._health.items()}

    def clear(self) -> None:
        self._health.clear()


class RecordStore:
    """Deduplicated final-record store with source-provenance merging."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, object]] = {}

    @staticmethod
    def _provenance(record: dict[str, object]) -> list[dict[str, str]]:
        provenance = record.get("source_provenance")
        return list(provenance) if isinstance(provenance, list) else []

    def store(self, key: str, record: dict[str, object]) -> str:
        """Store one record. Returns inserted/merged/upgraded/duplicate."""
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = record
            return "inserted"
        merged_provenance = self._provenance(existing)
        for entry in self._provenance(record):
            if entry not in merged_provenance:
                merged_provenance.append(entry)
        existing["source_provenance"] = merged_provenance
        if existing.get("verification_status") != "verified" and record.get("verification_status") == "verified":
            upgraded = dict(record)
            upgraded["source_provenance"] = merged_provenance
            self._records[key] = upgraded
            return "upgraded"
        return "duplicate"

    def records(self) -> list[dict[str, object]]:
        return list(self._records.values())

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def validate_discovery_config(adapter: "SourceAdapter") -> list[str]:
    """Return configuration errors for one adapter (empty when healthy).

    An enabled adapter MUST expose at least one valid discovery URL,
    otherwise production would silently skip the source.
    """
    errors: list[str] = []
    if not adapter.enabled:
        return errors
    if not adapter.discovery_urls:
        errors.append(f"[{adapter.source_id}] enabled but exposes no discovery_urls.")
        return errors
    for url in adapter.discovery_urls:
        if not _is_http_url(url):
            errors.append(f"[{adapter.source_id}] invalid discovery URL: {url!r}.")
    return errors


def find_adapter_for_url(
    adapters: list["SourceAdapter"], url: str, *, strict_domain: bool = True
) -> "SourceAdapter | None":
    """Route a fetched URL to its adapter without guessing.

    Strict pass: only adapters whose official domains (or explicit discovery
    URLs) cover the URL host may claim it. This prevents permissive matchers
    (for example Erasmus consortium programme hints) from stealing another
    source's record pages. Permissive pass (``strict_domain=False``) is the
    fallback for consortium programme pages on arbitrary university domains.
    A misbehaving adapter never blocks the remaining ones.
    """
    from .source_adapters.base import host_in_domains

    normalized = (url or "").strip().lower().rstrip("/")
    for adapter in adapters:
        try:
            if strict_domain:
                in_scope = host_in_domains(url, adapter.official_domains) or any(
                    normalized == item.strip().lower().rstrip("/") for item in adapter.discovery_urls
                )
                if not in_scope:
                    continue
            if adapter.is_listing_url(url) or adapter.is_detail_url(url):
                return adapter
        except Exception:
            continue
    return None


@dataclass
class DiscoveryPlan:
    """Pure scheduling outcome: which sources run and which URLs are fetched."""

    active_ids: list[str]
    per_source_urls: dict[str, list[str]]
    start_urls: list[str]
    warnings: list[str]

    @property
    def scheduled_total(self) -> int:
        return len(self.start_urls)


def plan_run(
    *,
    sources_input: list[str] | None,
    user_start_urls: list[str],
    adapters: list["SourceAdapter"],
) -> DiscoveryPlan:
    """Decide the run's discovery schedule from registry + input.

    - No ``sources`` input (or empty) → every enabled adapter is scheduled.
    - ``["all"]`` → every enabled adapter is scheduled.
    - Explicit ids → exactly those adapters, when they exist and are enabled.
    - Disabled or unknown ids produce warnings, never crashes.
    - Enabled adapters without a valid discovery URL are reported and skipped
      for this run instead of silently doing nothing.
    - User Start URLs are always preserved as additional discovery inputs.
    """
    by_id = {adapter.source_id: adapter for adapter in adapters}
    warnings: list[str] = []
    if not sources_input:
        wanted: set[str] = {adapter.source_id for adapter in adapters if adapter.enabled}
    else:
        selected = {item.strip().lower() for item in sources_input if item.strip()}
        if "all" in selected:
            wanted = {adapter.source_id for adapter in adapters if adapter.enabled}
        else:
            wanted = set(selected)
            for name in sorted(selected - set(by_id)):
                if name != "all":
                    warnings.append(f"Ignoring unknown source id: {name}.")
    active_ids: list[str] = []
    per_source_urls: dict[str, list[str]] = {}
    for adapter in adapters:
        if adapter.source_id not in wanted:
            continue
        if not adapter.enabled:
            warnings.append(
                f"Source '{adapter.source_id}' is disabled ({adapter.status_reason}); skipping."
            )
            continue
        errors = validate_discovery_config(adapter)
        if errors:
            warnings.extend(errors)
            continue
        urls = [url.strip() for url in adapter.discovery_urls if _is_http_url(url)]
        if not urls:
            warnings.append(f"Source '{adapter.source_id}' has no usable discovery URL; skipping.")
            continue
        active_ids.append(adapter.source_id)
        per_source_urls[adapter.source_id] = urls
    start_urls = list(dict.fromkeys(
        [url for source_id in active_ids for url in per_source_urls[source_id]]
        + [url for url in user_start_urls if url.strip()]
    ))
    return DiscoveryPlan(
        active_ids=active_ids,
        per_source_urls=per_source_urls,
        start_urls=start_urls,
        warnings=warnings,
    )


def build_limit_diagnostic(
    *,
    scheduled: int,
    enqueued: int,
    completed: int,
    limit: int,
    stats_total: int = 0,
) -> dict[str, object]:
    """Decide whether the crawler request limit truncated the run.

    ``enqueued`` counts every request the router scheduled (seeds plus
    discovery/official follow-ups); ``completed`` counts pages the handlers
    actually processed; ``stats_total`` is the crawler's own request total
    when readable. Truncation means pages remained unprocessed *because of*
    the cap: fewer pages completed than were known, while the cap was
    plausibly binding (completed, enqueued, or crawler totals reached it).
    A bare ``completed == limit`` comparison is not used, because failed
    requests and shutdown behavior can shift the numbers either way.
    """
    known_total = max(scheduled, enqueued, stats_total)
    cap_binding = completed >= limit or stats_total >= limit or enqueued >= limit
    reached = completed < known_total and cap_binding
    return {
        "request_limit": limit,
        "requests_scheduled": scheduled,
        "requests_completed": completed,
        "request_limit_reached": reached,
    }


def limit_diagnostic(scheduled: int, completed: int, limit: int) -> dict[str, object]:
    """Legacy wrapper kept for backwards compatibility; prefers the builder."""
    return build_limit_diagnostic(
        scheduled=scheduled, enqueued=scheduled, completed=completed, limit=limit
    )


def rejection_breakdown(items: list[dict[str, object]]) -> dict[str, int]:
    """Explain *why* runs yield zero strong matches (never weakens filtering)."""
    reasons: dict[str, int] = {
        "non_masters": 0,
        "not_fully_funded": 0,
        "field_mismatch": 0,
        "nationality_mismatch": 0,
        "destination_mismatch": 0,
        "abroad_restriction": 0,
        "expired": 0,
        "insufficient_evidence": 0,
    }
    for item in items:
        if str(item.get("match_status", "")) != "rejected":
            continue
        if str(item.get("degree_match", "")) == "excluded":
            reasons["non_masters"] += 1
        elif str(item.get("funding_status", "")) == "excluded":
            reasons["not_fully_funded"] += 1
        elif str(item.get("field_match", "")) == "excluded":
            reasons["field_mismatch"] += 1
        elif str(item.get("nationality_match", "")) == "excluded":
            reasons["nationality_mismatch"] += 1
        elif str(item.get("destination_match", "")) == "excluded":
            reasons["destination_mismatch"] += 1
        elif str(item.get("application_from_abroad", "")) == "excluded" or str(item.get("residence_match", "")) == "excluded":
            reasons["abroad_restriction"] += 1
        elif str(item.get("deadline_state", "")) == "expired":
            reasons["expired"] += 1
        else:
            reasons["insufficient_evidence"] += 1
    reasons["possible_matches"] = sum(1 for item in items if str(item.get("match_status", "")) == "possible_match")
    return reasons


def assemble_record(
    *,
    evaluated: dict[str, object],
    source_id: str,
    source_name: str,
    source_domain: str,
    source_type: str,
    title: str,
    discovery_url: str,
    official_url: str,
    canonical_url: str,
    official_source_domain: str,
    official_source_type: str,
    verification_status: str,
    discovery_fields: dict[str, str],
    official_fields: dict[str, str],
    display_fields: dict[str, str],
    student_profile: dict[str, object],
    provenance: list[dict[str, str]],
    discovery_timestamp: str,
    verification_timestamp: str,
) -> dict[str, object]:
    """Assemble one dataset record from evaluated evidence plus provenance."""
    return {
        "record_type": "scholarship",
        "title": title or "Unknown scholarship",
        "url": official_url or discovery_url,
        "discovery_url": discovery_url,
        "official_url": official_url,
        "canonical_url": canonical_url,
        "source_id": source_id,
        "source_name": source_name,
        "source_domain": source_domain,
        "source_type": source_type,
        "official_source_domain": official_source_domain,
        "official_source_type": official_source_type,
        "verification_status": verification_status,
        "degree_requirements": display_fields.get("degree", ""),
        "field_requirements": display_fields.get("field", ""),
        "nationality_requirements": display_fields.get("nationality", ""),
        "funding": display_fields.get("funding", ""),
        "cgpa_requirements": display_fields.get("cgpa", ""),
        "provider": display_fields.get("provider", ""),
        "discovery_evidence": discovery_fields,
        "official_evidence": official_fields,
        "source_provenance": provenance,
        "discovery_timestamp": discovery_timestamp,
        "verification_timestamp": verification_timestamp,
        "student_profile": student_profile,
        **evaluated,
    }
