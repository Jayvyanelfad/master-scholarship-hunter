"""Crawlee routes for adapter-driven discovery and official verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawlingContext
from crawlee.router import Router

from .pipeline import HealthTracker, RecordStore, assemble_record
from .profile_rules import STUDENT_PROFILE, analyze_degree, analyze_destination, evaluate_scholarship
from .source_adapters import build_adapters
from .source_adapters.base import SourceAdapter, dedup_key
from .source_adapters.wemakescholars import is_scholarship_url, is_wms
from .sources import source_by_url
from .verification import (
    LinkCandidate,
    canonical_url,
    extract_structured_fields,
    is_acceptable_official_link,
    merge_fields,
    official_source_type,
    select_official_url,
)

router = Router[BeautifulSoupCrawlingContext]()

_ALL_ADAPTERS: list[SourceAdapter] = build_adapters()
_ACTIVE_ADAPTERS: list[SourceAdapter] = [adapter for adapter in _ALL_ADAPTERS if adapter.enabled]
_MAX_PER_SOURCE = 50
_VERIFY_OFFICIAL = True

_health = HealthTracker()
_store = RecordStore()
_stored_per_source: dict[str, int] = {}
_pending_by_official_url: dict[str, list["PendingDiscovery"]] = {}


def configure_routing(*, source_ids: list[str] | None = None, max_per_source: int = 50, verify_official: bool = True) -> list[str]:
    """Select active adapters for a run. Returns the active source ids."""
    global _ACTIVE_ADAPTERS, _MAX_PER_SOURCE, _VERIFY_OFFICIAL
    _MAX_PER_SOURCE = max(1, int(max_per_source))
    _VERIFY_OFFICIAL = bool(verify_official)
    if not source_ids:
        _ACTIVE_ADAPTERS = [adapter for adapter in _ALL_ADAPTERS if adapter.enabled]
    else:
        wanted = {item.strip().lower() for item in source_ids if item.strip()}
        if "all" in wanted:
            _ACTIVE_ADAPTERS = list(_ALL_ADAPTERS)
        else:
            _ACTIVE_ADAPTERS = [adapter for adapter in _ALL_ADAPTERS if adapter.source_id in wanted]
    # Disabled adapters stay inactive even under "all": they log their reason.
    _ACTIVE_ADAPTERS = [adapter for adapter in _ACTIVE_ADAPTERS if adapter.enabled]
    return [adapter.source_id for adapter in _ACTIVE_ADAPTERS]


def reset_deduplication() -> None:
    _pending_by_official_url.clear()
    _store.clear()
    _stored_per_source.clear()
    _health.clear()


def get_source_health() -> dict[str, dict[str, object]]:
    return _health.as_dicts()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class PendingDiscovery:
    discovery_id: str
    title: str
    discovery_url: str
    fields: dict[str, str]
    official_url: str
    source_id: str = "wemakescholars"
    source_name: str = "WeMakeScholars"
    residence_countries: str = ""
    requirement_text: str = ""
    discovered_at: str = ""


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def page_text(context: BeautifulSoupCrawlingContext) -> str:
    return clean_text(context.soup.get_text(" ", strip=True))


def _adapter_for_url(url: str) -> SourceAdapter | None:
    for adapter in _ACTIVE_ADAPTERS:
        try:
            if adapter.is_listing_url(url) or adapter.is_detail_url(url):
                return adapter
        except Exception:
            continue
    registered = source_by_url(url)
    if registered:
        for adapter in _ACTIVE_ADAPTERS:
            if adapter.source_id == registered.identifier:
                return adapter
    return None


def _source_metadata(url: str) -> tuple[str, str]:
    if is_wms(url):
        return "WeMakeScholars", "reputable_aggregator"
    registered = source_by_url(url)
    if registered and registered.source_type.startswith("official_"):
        return registered.name, registered.source_type
    return (urlparse(url).hostname or "Official source"), official_source_type(url)


def _candidate_links(context: BeautifulSoupCrawlingContext) -> list[LinkCandidate]:
    return [
        LinkCandidate(str(link.get("href") or ""), clean_text(link.get_text(" ", strip=True)))
        for link in context.soup.select("a[href]")
    ]


def _discovery_id(url: str, title: str, provider: str) -> str:
    return "|".join((canonical_url(url), clean_text(title).lower(), clean_text(provider).lower()))


def _evaluate_record(
    *,
    title: str,
    evidence_url: str,
    source_type: str,
    fields: dict[str, str],
    verification_status: str,
    residence_countries: str = "",
    requirement_text: str = "",
) -> dict[str, object]:
    return evaluate_scholarship(
        title=title, url=evidence_url, source_type=source_type,
        degree=fields.get("degree", ""), field=fields.get("field", ""), funding=fields.get("funding", ""),
        nationality=fields.get("nationality", ""), destination=fields.get("destination", ""),
        application_location=fields.get("application_location", ""), deadline=fields.get("deadline", ""),
        cgpa_requirements=fields.get("cgpa", ""), verification_status=verification_status,
        residence_countries=residence_countries, requirement_text=requirement_text,
    )


def _provenance(source_id: str, source_name: str, discovery_url: str, role: str) -> list[dict[str, str]]:
    return [{"source_id": source_id, "source_name": source_name, "discovery_url": discovery_url, "role": role}]


def _store_evaluated(
    *,
    source_id: str,
    source_name: str,
    candidate: PendingDiscovery,
    official_url: str,
    official_fields: dict[str, str],
    verification_status: str,
    official_source_domain: str,
    official_source_type: str,
) -> None:
    health = _health.record(source_id, source_name)
    if _stored_per_source.get(source_id, 0) >= _MAX_PER_SOURCE:
        health.note = f"Per-source cap reached ({_MAX_PER_SOURCE} records)."
        return
    if verification_status == "verified":
        result = _evaluate_record(
            title=candidate.title, evidence_url=official_url or candidate.discovery_url,
            source_type=official_source_type or "reputable_aggregator",
            fields=official_fields, verification_status="verified",
            residence_countries=candidate.residence_countries, requirement_text=candidate.requirement_text,
        )
        display = merge_fields(candidate.fields, official_fields)
    else:
        result = _evaluate_record(
            title=candidate.title, evidence_url=candidate.discovery_url,
            source_type="reputable_aggregator" if candidate.source_id == "wemakescholars" else official_source_type,
            fields=candidate.fields, verification_status="unverified",
            residence_countries=candidate.residence_countries, requirement_text=candidate.requirement_text,
        )
        display = dict(candidate.fields)
    record = assemble_record(
        evaluated=result, source_id=source_id, source_name=source_name,
        source_domain=urlparse(candidate.discovery_url).hostname or "",
        source_type="reputable_aggregator" if candidate.source_id == "wemakescholars" else official_source_type,
        title=candidate.title, discovery_url=candidate.discovery_url,
        official_url=official_url, canonical_url=canonical_url(candidate.discovery_url),
        official_source_domain=official_source_domain, official_source_type=official_source_type,
        verification_status=verification_status, discovery_fields=candidate.fields,
        official_fields=official_fields, display_fields=display,
        student_profile=STUDENT_PROFILE,
        provenance=_provenance(source_id, source_name, candidate.discovery_url, "verification" if verification_status == "verified" else "discovery"),
        discovery_timestamp=candidate.discovered_at or _now(),
        verification_timestamp=_now() if verification_status == "verified" else "",
    )
    key = dedup_key(candidate.title, display.get("provider", ""), display.get("destination", ""), official_url if verification_status == "verified" else "", candidate.discovery_url)
    outcome = _store.store(key, record)
    if outcome in {"inserted", "upgraded"}:
        _stored_per_source[source_id] = _stored_per_source.get(source_id, 0) + 1
    status = str(result.get("match_status", ""))
    if status == "strong_match":
        health.verified += 1
    elif status == "rejected":
        health.rejected += 1
    else:
        health.possible += 1


def _unverified_warning(candidate: PendingDiscovery, warning: str) -> None:
    for record in _store.records():
        if record.get("discovery_url") == candidate.discovery_url and record.get("verification_status") == "unverified":
            warnings = list(record.get("warnings", []))
            if warning not in warnings:
                warnings.append(warning)
                record["warnings"] = warnings
            break


def _prescreen_reject(fields: dict[str, str]) -> str:
    """Return a reason when official verification is pointless, else "".

    Only obvious hard exclusions skip the official hop (wrong degree level or
    excluded destination). Everything else still gets verified, because the
    official page may clarify ambiguous discovery evidence.
    """
    degree_match, _ = analyze_degree(fields.get("degree", ""), "", "reputable_aggregator")
    if degree_match == "excluded":
        return "Pre-screened: discovery evidence already excludes the degree level; official fetch skipped."
    destination_match, _ = analyze_destination(fields.get("destination", ""), "", "reputable_aggregator")
    if destination_match == "excluded":
        return "Pre-screened: discovery evidence already excludes the destination; official fetch skipped."
    return ""


@router.handler("SCHOLARSHIP")
async def scholarship_handler(context: BeautifulSoupCrawlingContext) -> None:
    discovery_url, soup = str(context.request.url), context.soup
    title = clean_text(soup.h1.get_text(" ", strip=True) if soup.h1 else (soup.title.get_text(" ", strip=True) if soup.title else ""))
    fields = extract_structured_fields(page_text(context))
    official_url = select_official_url(discovery_url, fields.get("provider", ""), _candidate_links(context))
    candidate = PendingDiscovery(_discovery_id(discovery_url, title, fields.get("provider", "")), title, discovery_url, fields, official_url or "", discovered_at=_now())

    if not official_url:
        _store_evaluated(source_id="wemakescholars", source_name="WeMakeScholars", candidate=candidate, official_url="", official_fields={}, verification_status="unverified", official_source_domain="", official_source_type="")
        _unverified_warning(candidate, "No legitimate official verification URL was found on the discovery page.")
        Actor.log.info(f"Scholarship processed without official verification: {title[:80]}")
        return

    if not _VERIFY_OFFICIAL:
        _store_evaluated(source_id="wemakescholars", source_name="WeMakeScholars", candidate=candidate, official_url=official_url, official_fields={}, verification_status="unverified", official_source_domain="", official_source_type="")
        _unverified_warning(candidate, "Official verification disabled for this run (verify_official=false).")
        return

    prescreen = _prescreen_reject(fields)
    if prescreen:
        _store_evaluated(source_id="wemakescholars", source_name="WeMakeScholars", candidate=candidate, official_url=official_url, official_fields={}, verification_status="unverified", official_source_domain="", official_source_type="")
        _unverified_warning(candidate, prescreen)
        Actor.log.info(f"Scholarship pre-screened without official fetch: {title[:80]}")
        return

    _pending_by_official_url.setdefault(canonical_url(official_url), []).append(candidate)
    _health.record("wemakescholars", "WeMakeScholars").official_queued += 1
    # Crawlee requires URL strings here; association is held by canonical URL.
    await context.add_requests([official_url])
    Actor.log.info(f"Official verification queued: {title[:80]} -> {official_url}")


@router.handler("OFFICIAL")
async def official_handler(context: BeautifulSoupCrawlingContext) -> None:
    official_url = canonical_url(str(context.request.url))
    candidates = _pending_by_official_url.pop(official_url, [])
    if not candidates:
        return
    official_fields = extract_structured_fields(page_text(context))
    for candidate in candidates:
        _health.record(candidate.source_id, candidate.source_name).official_fetched += 1
        official_name, official_type = _source_metadata(str(context.request.url))
        _store_evaluated(
            source_id=candidate.source_id, source_name=candidate.source_name,
            candidate=candidate, official_url=str(context.request.url), official_fields=official_fields,
            verification_status="verified", official_source_domain=urlparse(str(context.request.url)).hostname or "",
            official_source_type=official_type,
        )
        Actor.log.info(f"Official evidence merged: {candidate.title[:80]} | {official_url}")


@router.handler("ADAPTER_LISTING")
async def adapter_listing_handler(context: BeautifulSoupCrawlingContext) -> None:
    url = str(context.request.url)
    adapter = _adapter_for_url(url)
    if adapter is None:
        await start_handler(context)
        return
    health = _health.record(adapter.source_id, adapter.display_name)
    health.attempted += 1
    try:
        html = str(context.soup)
        result = adapter.parse_listing(html, url)
    except Exception as error:
        _health.fail(adapter.source_id, adapter.display_name, f"Listing parse failed: {error}")
        Actor.log.warning(f"Source {adapter.source_id} listing failed: {error}")
        return
    queued = 0
    for candidate in result.candidates:
        if _stored_per_source.get(adapter.source_id, 0) + queued >= min(adapter.max_records, _MAX_PER_SOURCE):
            break
        try:
            await context.add_requests([candidate.url])
            queued += 1
        except Exception as error:
            _health.fail(adapter.source_id, adapter.display_name, f"Enqueue failed: {error}")
            break
    health.discovered += queued
    Actor.log.info(f"Source {adapter.source_id}: {queued} detail URL(s) queued from listing.")


@router.handler("ADAPTER_DETAIL")
async def adapter_detail_handler(context: BeautifulSoupCrawlingContext) -> None:
    url = str(context.request.url)
    adapter = _adapter_for_url(url)
    if adapter is None:
        return
    health = _health.record(adapter.source_id, adapter.display_name)
    try:
        detail = adapter.parse_detail(str(context.soup), url)
    except Exception as error:
        _health.fail(adapter.source_id, adapter.display_name, f"Detail parse failed: {error}")
        Actor.log.warning(f"Source {adapter.source_id} detail failed for {url}: {error}")
        return
    candidate = PendingDiscovery(
        _discovery_id(url, detail.title, detail.fields.get("provider", "")),
        detail.title, url, detail.fields, "",
        source_id=adapter.source_id, source_name=adapter.display_name,
        residence_countries=detail.residence_countries, requirement_text=detail.requirement_text,
        discovered_at=_now(),
    )
    if detail.is_hop:
        # Index/catalogue page: no record stored, only deeper official
        # follow-ups are queued below.
        pass
    elif adapter.detail_is_official:
        official_type = adapter.source_type if adapter.source_type.startswith("official_") else official_source_type(url)
        _store_evaluated(
            source_id=adapter.source_id, source_name=adapter.display_name, candidate=candidate,
            official_url=url, official_fields=detail.fields, verification_status="verified",
            official_source_domain=urlparse(url).hostname or "", official_source_type=official_type,
        )
        health.official_fetched += 1
        for note in detail.notes:
            _unverified_warning_note(url, note)
    else:
        _store_evaluated(
            source_id=adapter.source_id, source_name=adapter.display_name, candidate=candidate,
            official_url="", official_fields={}, verification_status="unverified",
            official_source_domain="", official_source_type="",
        )
    # Follow-ups were explicitly selected by the adapter's own policy
    # (partner routes, programme pages); the shared gate still rejects any
    # social/tracking/same-page link that slipped through.
    follow = [link for link in detail.follow_links if is_acceptable_official_link(link, url)]
    if _VERIFY_OFFICIAL:
        for link in follow[:15]:
            _pending_by_official_url.setdefault(canonical_url(link), []).append(
                PendingDiscovery(
                    candidate.discovery_id, candidate.title, candidate.discovery_url,
                    candidate.fields, link, source_id=adapter.source_id,
                    source_name=adapter.display_name,
                    residence_countries=candidate.residence_countries,
                    requirement_text=candidate.requirement_text, discovered_at=candidate.discovered_at,
                )
            )
            health.official_queued += 1
            await context.add_requests([link])
    Actor.log.info(f"Source {adapter.source_id} detail processed: {detail.title[:80]}")


def _unverified_warning_note(discovery_url: str, warning: str) -> None:
    for record in _store.records():
        if record.get("discovery_url") == discovery_url or record.get("official_url") == discovery_url:
            warnings = list(record.get("warnings", []))
            if warning not in warnings:
                warnings.append(warning)
                record["warnings"] = warnings
            break


@router.handler("START")
async def start_handler(context: BeautifulSoupCrawlingContext) -> None:
    current_url, found = str(context.request.url), 0
    for link in context.soup.select("a[href]"):
        absolute_url = urljoin(current_url, str(link.get("href") or ""))
        if is_scholarship_url(absolute_url):
            await context.add_requests([absolute_url])
            found += 1
    Actor.log.info(f"Found {found} individual scholarship URL(s).")


@router.default_handler
async def default_handler(context: BeautifulSoupCrawlingContext) -> None:
    url = str(context.request.url)
    try:
        if canonical_url(url) in _pending_by_official_url:
            await official_handler(context)
            return
        if is_scholarship_url(url):
            await scholarship_handler(context)
            return
        adapter = _adapter_for_url(url)
        if adapter is not None:
            try:
                if adapter.is_detail_url(url):
                    await adapter_detail_handler(context)
                else:
                    await adapter_listing_handler(context)
            except Exception as error:
                _health.fail(adapter.source_id, adapter.display_name, f"Handler failed: {error}")
                Actor.log.warning(f"Source {adapter.source_id} failed for {url}: {error}")
            return
        await start_handler(context)
    except Exception as error:
        Actor.log.warning(f"Request failed for {url}: {error}")


def drain_final_records() -> list[dict[str, object]]:
    """Return merged results and retain unverified records when an official fetch fails."""
    for candidates in _pending_by_official_url.values():
        for candidate in candidates:
            official_name, official_type = _source_metadata(candidate.official_url or candidate.discovery_url)
            _store_evaluated(
                source_id=candidate.source_id, source_name=candidate.source_name,
                candidate=candidate, official_url=candidate.official_url, official_fields={},
                verification_status="unverified", official_source_domain="", official_source_type="",
            )
            _unverified_warning(candidate, "Official verification page could not be fetched or processed.")
    _pending_by_official_url.clear()
    records = _store.records()
    _store.clear()
    return records
