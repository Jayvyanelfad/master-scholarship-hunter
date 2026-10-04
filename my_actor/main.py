"""Main entry point for Master Scholarship Hunter."""

from __future__ import annotations

import asyncio

from apify import Actor, Event
from crawlee.crawlers import BeautifulSoupCrawler

from .pipeline import limit_diagnostic, plan_run, rejection_breakdown
from .routes import router
from .routes import configure_routing
from .routes import drain_final_records
from .routes import get_requests_seen
from .routes import get_source_health
from .routes import reset_deduplication
from .source_adapters import build_adapters
from .sources import status_table

DEFAULT_START_URL = (
    "https://www.wemakescholars.com/"
    "Masters-scholarships-in-computer-sciences-and-information-technology-to-study-abroad"
)


async def main() -> None:
    async with Actor:

        async def on_aborting() -> None:
            await asyncio.sleep(1)
            await Actor.exit()

        Actor.on(Event.ABORTING, on_aborting)

        actor_input = await Actor.get_input() or {}

        raw_sources = actor_input.get("sources", None)
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        max_per_source = actor_input.get("max_results_per_source", 50)
        try:
            max_per_source = int(max_per_source)
        except (TypeError, ValueError):
            max_per_source = 50
        verify_official = actor_input.get("verify_official", True)
        if isinstance(verify_official, str):
            verify_official = verify_official.strip().lower() not in {"false", "0", "no", "off"}

        raw_start_urls = actor_input.get(
            "start_urls",
            [{"url": DEFAULT_START_URL}],
        )
        max_requests = actor_input.get("max_requests_per_crawl", 300)
        try:
            request_limit = max(1, int(max_requests))
        except (TypeError, ValueError):
            request_limit = 300

        user_start_urls: list[str] = []
        for item in raw_start_urls:
            if isinstance(item, str):
                if item.strip():
                    user_start_urls.append(item.strip())

            elif isinstance(item, dict):
                url = item.get("url")

                if isinstance(url, str) and url.strip():
                    user_start_urls.append(url.strip())

        # Remove duplicates while preserving order.
        user_start_urls = list(dict.fromkeys(user_start_urls))

        # The source registry is authoritative: by default every enabled
        # adapter is scheduled. User Start URLs are additional legacy inputs;
        # they never suppress registry-driven discovery.
        plan = plan_run(
            sources_input=raw_sources if isinstance(raw_sources, list) else None,
            user_start_urls=user_start_urls,
            adapters=build_adapters(),
        )
        configure_routing(
            source_ids=plan.active_ids,
            max_per_source=max_per_source,
            verify_official=bool(verify_official),
        )

        Actor.log.info(f"Configured start URLs: {len(user_start_urls)}")
        Actor.log.info(f"Enabled source adapters: {len(plan.active_ids)}")
        Actor.log.info("Discovery sources:")
        for source_id in plan.active_ids:
            Actor.log.info(f"- {source_id}")
        Actor.log.info(f"Discovery requests scheduled: {plan.scheduled_total}")
        for warning in plan.warnings:
            Actor.log.warning(warning)
        for source_id in plan.active_ids:
            Actor.log.info(
                f"[Source: {source_id}] Starting discovery "
                f"({len(plan.per_source_urls[source_id])} page(s))."
            )
        for entry in status_table():
            if entry["source_id"] not in set(plan.active_ids):
                Actor.log.info(
                    f"[Source: {entry['source_id']}] skipped ({entry['status']}). {entry['reason']}"
                )

        if not plan.start_urls:
            Actor.log.error("No discovery URLs scheduled and no start URLs supplied.")
            return

        reset_deduplication()
        Actor.log.info(f"Request limit: {request_limit}")
        Actor.log.info(f"Requests scheduled: {plan.scheduled_total}")
        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=request_limit,
            request_handler=router,
        )

        try:
            await crawler.run(plan.start_urls)
        except Exception as error:
            Actor.log.error(f"Crawler run failed: {error}")

        requests_completed = get_requests_seen()
        Actor.log.info(f"Requests completed: {requests_completed}")
        crawling = limit_diagnostic(plan.scheduled_total, requests_completed, request_limit)
        if crawling["request_limit_reached"]:
            Actor.log.warning(
                f"Request limit reached ({request_limit}): the research set may be "
                f"truncated. Raise max_requests_per_crawl to cover all discovery "
                f"and verification requests."
            )

        # Routes hold discovery records until official evidence is merged, so
        # each dataset item is one final scholarship record.
        for record in drain_final_records():
            try:
                await Actor.push_data(record)
            except Exception as error:
                Actor.log.warning(f"Failed to push a record, continuing: {error}")

        # Read the final scholarship records produced by this Actor run.
        dataset = await Actor.open_dataset()
        dataset_data = await dataset.get_data()
        scholarship_items = list(dataset_data.items)
        health = get_source_health()

        reasons = rejection_breakdown(scholarship_items)
        diagnostics = {
            "scholarships_discovered": len(scholarship_items),
            "scholarships_verified": sum(item.get("verification_status") == "verified" for item in scholarship_items),
            "rejected": sum(item.get("match_status") == "rejected" for item in scholarship_items),
            "possible_matches": sum(item.get("match_status") == "possible_match" for item in scholarship_items),
            "expired": sum(item.get("deadline_state") == "expired" for item in scholarship_items),
            "funding_unknown": sum(item.get("funding_status") == "unknown" for item in scholarship_items),
            "nationality_unknown": sum(item.get("nationality_match") == "unknown" for item in scholarship_items),
            "destination_unknown": sum(item.get("destination_match") == "unknown" for item in scholarship_items),
            "strong_matches": sum(item.get("match_status") == "strong_match" for item in scholarship_items),
            "official_pages_checked": sum(entry.get("official_fetched", 0) for entry in health.values()),
            "source_errors": sum(entry.get("errors", 0) for entry in health.values()),
            "request_limit": crawling["request_limit"],
            "requests_scheduled": crawling["requests_scheduled"],
            "requests_completed": crawling["requests_completed"],
            "request_limit_reached": crawling["request_limit_reached"],
            **{f"reason_{key}": value for key, value in reasons.items()},
        }
        Actor.log.info("Run diagnostics: " + ", ".join(f"{key}={value}" for key, value in diagnostics.items()))
        Actor.log.info("Source health summary:")
        for source_id in plan.active_ids:
            entry = health.get(source_id, {})
            discovered = entry.get("discovered", 0)
            Actor.log.info(
                f"{source_id}: discovered={discovered} "
                f"official_pages_checked={entry.get('official_fetched', 0)} "
                f"evidence_verified={entry.get('verified', 0)} "
                f"possible_matches={entry.get('possible', 0)} "
                f"strong_matches={entry.get('strong_matches', 0)} "
                f"rejected={entry.get('rejected', 0)} "
                f"errors={entry.get('errors', 0)} {entry.get('note', '')}".rstrip()
            )
            if not entry or not discovered:
                Actor.log.info(f"[Source: {source_id}] discovered {discovered} candidates.")
        for source_id, entry in health.items():
            if source_id not in set(plan.active_ids):
                Actor.log.info(
                    f"{source_id}: discovered={entry.get('discovered', 0)} "
                    f"errors={entry.get('errors', 0)} {entry.get('note', '')}".rstrip()
                )

        # Send the daily email digest.
        from .emailer import send_scholarship_email

        await send_scholarship_email(scholarship_items, diagnostics, health)

        Actor.log.info("Scholarship email sent successfully.")

        Actor.log.info("Master Scholarship Hunter finished successfully.")


if __name__ == "__main__":
    asyncio.run(main())
