"""Crawlee routes for WMS discovery and official-source verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawlingContext
from crawlee.router import Router

from .profile_rules import STUDENT_PROFILE, evaluate_scholarship
from .sources import source_by_url
from .verification import (
    LinkCandidate,
    canonical_url,
    extract_structured_fields,
    merge_fields,
    official_source_type,
    select_official_url,
)

router = Router[BeautifulSoupCrawlingContext]()
WMS_DOMAINS = {"www.wemakescholars.com", "wemakescholars.com", "zeta.wemakescholars.com"}
SCHOLARSHIP_PATH_MARKERS = ("/scholarship/", "/scholarships/")


@dataclass(frozen=True)
class PendingDiscovery:
    discovery_id: str
    title: str
    discovery_url: str
    fields: dict[str, str]
    official_url: str


_pending_by_official_url: dict[str, list[PendingDiscovery]] = {}
_final_records: list[dict[str, object]] = []
_seen_ids: set[str] = set()


def reset_deduplication() -> None:
    _pending_by_official_url.clear()
    _final_records.clear()
    _seen_ids.clear()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_wms(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in WMS_DOMAINS


def is_scholarship_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and is_wms(url) and any(marker in parsed.path.lower() for marker in SCHOLARSHIP_PATH_MARKERS)


def page_text(context: BeautifulSoupCrawlingContext) -> str:
    return clean_text(context.soup.get_text(" ", strip=True))


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


def _evaluate_record(*, title: str, evidence_url: str, source_type: str, fields: dict[str, str], verification_status: str) -> dict[str, object]:
    return evaluate_scholarship(
        title=title, url=evidence_url, source_type=source_type,
        degree=fields["degree"], field=fields["field"], funding=fields["funding"],
        nationality=fields["nationality"], destination=fields["destination"],
        application_location=fields["application_location"], deadline=fields["deadline"],
        cgpa_requirements=fields["cgpa"], verification_status=verification_status,
    )


def _queue_final(record: dict[str, object], discovery_id: str) -> None:
    if discovery_id not in _seen_ids:
        _seen_ids.add(discovery_id)
        _final_records.append(record)


def _unverified_record(candidate: PendingDiscovery, warning: str = "") -> dict[str, object]:
    result = _evaluate_record(
        title=candidate.title, evidence_url=candidate.discovery_url,
        source_type="reputable_aggregator", fields=candidate.fields, verification_status="unverified",
    )
    warnings = list(result["warnings"])
    if warning:
        warnings.append(warning)
    return {
        "record_type": "scholarship", "title": candidate.title or "Unknown scholarship",
        "url": candidate.discovery_url, "discovery_url": candidate.discovery_url,
        "official_url": candidate.official_url, "canonical_url": canonical_url(candidate.discovery_url),
        "source_name": "WeMakeScholars", "source_domain": urlparse(candidate.discovery_url).hostname or "",
        "source_type": "reputable_aggregator", "official_source_domain": "",
        "official_source_type": "", "verification_status": "unverified",
        "degree_requirements": candidate.fields["degree"], "field_requirements": candidate.fields["field"],
        "nationality_requirements": candidate.fields["nationality"], "funding": candidate.fields["funding"],
        "cgpa_requirements": candidate.fields["cgpa"], "provider": candidate.fields["provider"],
        "discovery_evidence": candidate.fields, "official_evidence": {}, "student_profile": STUDENT_PROFILE,
        **result, "warnings": warnings,
    }


def _verified_record(candidate: PendingDiscovery, official_url: str, official_fields: dict[str, str]) -> dict[str, object]:
    official_name, official_type = _source_metadata(official_url)
    # Match using official evidence only. This prevents an omitted official
    # benefit/restriction from being filled by an aggregator claim.
    result = _evaluate_record(
        title=candidate.title, evidence_url=official_url, source_type=official_type,
        fields=official_fields, verification_status="verified",
    )
    merged = merge_fields(candidate.fields, official_fields)
    return {
        "record_type": "scholarship", "title": candidate.title or "Unknown scholarship",
        "url": official_url, "discovery_url": candidate.discovery_url, "official_url": official_url,
        "canonical_url": canonical_url(candidate.discovery_url), "source_name": "WeMakeScholars",
        "source_domain": urlparse(candidate.discovery_url).hostname or "", "source_type": "reputable_aggregator",
        "official_source_domain": urlparse(official_url).hostname or "", "official_source_type": official_type,
        "verification_status": "verified", "degree_requirements": merged["degree"],
        "field_requirements": merged["field"], "nationality_requirements": merged["nationality"],
        "funding": merged["funding"], "cgpa_requirements": merged["cgpa"], "provider": merged["provider"],
        "discovery_evidence": candidate.fields, "official_evidence": official_fields,
        "student_profile": STUDENT_PROFILE, **result,
    }


@router.handler("SCHOLARSHIP")
async def scholarship_handler(context: BeautifulSoupCrawlingContext) -> None:
    discovery_url, soup = str(context.request.url), context.soup
    title = clean_text(soup.h1.get_text(" ", strip=True) if soup.h1 else (soup.title.get_text(" ", strip=True) if soup.title else ""))
    fields = extract_structured_fields(page_text(context))
    official_url = select_official_url(discovery_url, fields["provider"], _candidate_links(context))
    candidate = PendingDiscovery(_discovery_id(discovery_url, title, fields["provider"]), title, discovery_url, fields, official_url or "")

    if not official_url:
        _queue_final(_unverified_record(candidate, "No legitimate official verification URL was found on the discovery page."), candidate.discovery_id)
        Actor.log.info(f"Scholarship processed without official verification: {title[:80]}")
        return

    _pending_by_official_url.setdefault(canonical_url(official_url), []).append(candidate)
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
        _queue_final(_verified_record(candidate, official_url, official_fields), candidate.discovery_id)
        Actor.log.info(f"Official evidence merged: {candidate.title[:80]} | {official_url}")


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
    if is_scholarship_url(url):
        await scholarship_handler(context)
    elif canonical_url(url) in _pending_by_official_url:
        await official_handler(context)
    else:
        await start_handler(context)


def drain_final_records() -> list[dict[str, object]]:
    """Return merged results and retain unverified records when an official fetch fails."""
    for candidates in _pending_by_official_url.values():
        for candidate in candidates:
            _queue_final(_unverified_record(candidate, "Official verification page could not be fetched or processed."), candidate.discovery_id)
    _pending_by_official_url.clear()
    records = list(_final_records)
    _final_records.clear()
    return records
