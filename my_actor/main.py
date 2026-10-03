"""Main entry point for Master Scholarship Hunter."""

from __future__ import annotations

import asyncio

from apify import Actor, Event
from crawlee.crawlers import BeautifulSoupCrawler

from .pipeline import rejection_breakdown
from .routes import router
from .routes import configure_routing
from .routes import drain_final_records
from .routes import get_source_health
from .routes import reset_deduplication
from .sources import configured_sources, status_table

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
        max_requests = actor_input.get("max_requests_per_crawl", 100)

        # Production default: every enabled source adapter. An explicit
        # "sources" list (or ["all"]) overrides the default; unknown ids are
        # ignored with a log line instead of crashing the run.
        active_ids = configure_routing(
            source_ids=raw_sources if isinstance(raw_sources, list) else None,
            max_per_source=max_per_source,
            verify_official=bool(verify_official),
        )
        selected = configured_sources(raw_sources if isinstance(raw_sources, list) else None)
        selected_ids = {source.identifier for source in selected}
        unknown = (
            {item.strip().lower() for item in raw_sources if isinstance(item, str) and item.strip()}
            if isinstance(raw_sources, list) else set()
        ) - selected_ids - {"all"}
        for name in sorted(unknown):
            Actor.log.warning(f"Ignoring unknown source id: {name}")

        start_urls: list[str] = []
        for source in selected:
            if source.identifier in set(active_ids):
                start_urls.extend(source.base_urls)

        for item in raw_start_urls:
            if isinstance(item, str):
                if item.strip():
                    start_urls.append(item.strip())

            elif isinstance(item, dict):
                url = item.get("url")

                if isinstance(url, str) and url.strip():
                    start_urls.append(url.strip())

        # Remove duplicates while preserving order.
        start_urls = list(dict.fromkeys(start_urls))

        if not start_urls:
            Actor.log.error("No start URLs supplied.")
            return

        Actor.log.info(
            f"Starting Master Scholarship Hunter with "
            f"{len(start_urls)} start URL(s) across {len(active_ids)} source(s): "
            f"{', '.join(active_ids) or 'none'}."
        )
        for entry in status_table():
            Actor.log.info(
                f"Source {entry['source_id']}: {entry['status']} "
                f"(discovery {entry['discovery']}, verification {entry['verification']}). "
                f"{entry['reason']}"
            )

        reset_deduplication()
        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=max(1, int(max_requests)) if isinstance(max_requests, int) else 100,
            request_handler=router,
        )

        try:
            await crawler.run(start_urls)
        except Exception as error:
            Actor.log.error(f"Crawler run failed: {error}")

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
            **{f"reason_{key}": value for key, value in reasons.items()},
        }
        Actor.log.info("Run diagnostics: " + ", ".join(f"{key}={value}" for key, value in diagnostics.items()))
        for source_id, entry in health.items():
            Actor.log.info(
                f"Source {source_id}: attempted={entry.get('attempted')} "
                f"discovered={entry.get('discovered')} official_queued={entry.get('official_queued')} "
                f"official_fetched={entry.get('official_fetched')} verified={entry.get('verified')} "
                f"possible={entry.get('possible')} rejected={entry.get('rejected')} "
                f"errors={entry.get('errors')} {entry.get('note', '')}"
            )

        # Send the daily email digest.
        from .emailer import send_scholarship_email

        await send_scholarship_email(scholarship_items, diagnostics, health)

        Actor.log.info("Scholarship email sent successfully.")

        Actor.log.info("Master Scholarship Hunter finished successfully.")


if __name__ == "__main__":
    asyncio.run(main())
