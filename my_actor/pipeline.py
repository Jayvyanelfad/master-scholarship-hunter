"""Crawler-independent pipeline state: health, deduplicated store, diagnostics.

This module has no Apify/Crawlee imports so unit tests can cover source
failure isolation, cross-source deduplication, and zero-result diagnostics
without a browser or network. ``my_actor.routes`` wires these pieces into
the live crawl.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field


@dataclass
class SourceHealth:
    """Per-source counters for one run (see task: source-level logging)."""

    source_id: str
    display_name: str = ""
    attempted: int = 0
    discovered: int = 0
    official_queued: int = 0
    official_fetched: int = 0
    verified: int = 0
    possible: int = 0
    rejected: int = 0
    errors: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "attempted": self.attempted,
            "discovered": self.discovered,
            "official_queued": self.official_queued,
            "official_fetched": self.official_fetched,
            "verified": self.verified,
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
