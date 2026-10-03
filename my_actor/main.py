"""Main entry point for Master Scholarship Hunter."""

from __future__ import annotations

import asyncio

from apify import Actor, Event
from crawlee.crawlers import BeautifulSoupCrawler

from .routes import router
from .routes import drain_final_records
from .routes import reset_deduplication

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

        raw_start_urls = actor_input.get(
            "start_urls",
            [{"url": DEFAULT_START_URL}],
        )
        max_requests = actor_input.get("max_requests_per_crawl", 100)

        start_urls: list[str] = []

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
            f"{len(start_urls)} start URL(s)."
        )

        reset_deduplication()
        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=max(1, int(max_requests)) if isinstance(max_requests, int) else 100,
            request_handler=router,
        )

        await crawler.run(start_urls)

        # Routes hold discovery records until official evidence is merged, so
        # each dataset item is one final scholarship record.
        for record in drain_final_records():
            await Actor.push_data(record)

        # Read the final scholarship records produced by this Actor run.
        dataset = await Actor.open_dataset()
        dataset_data = await dataset.get_data()
        scholarship_items = list(dataset_data.items)

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
        }
        Actor.log.info("Run diagnostics: " + ", ".join(f"{key}={value}" for key, value in diagnostics.items()))

        # Send the daily email digest.
        from .emailer import send_scholarship_email

        await send_scholarship_email(scholarship_items, diagnostics)

        Actor.log.info("Scholarship email sent successfully.")

        Actor.log.info("Master Scholarship Hunter finished successfully.")


if __name__ == "__main__":
    asyncio.run(main())
