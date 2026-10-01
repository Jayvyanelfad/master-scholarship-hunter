"""Main entry point for the Master Scholarship Hunter."""

from __future__ import annotations

import asyncio

from apify import Actor, Event
from crawlee.crawlers import BeautifulSoupCrawler

from .routes import router


DEFAULT_START_URL = (
    "https://www.wemakescholars.com/"
    "Masters-scholarships-in-computer-sciences-and-information-technology-to-study-abroad"
)


async def main() -> None:
    """Run the scholarship crawler."""

    async with Actor:

        # ----------------------------------------------------
        # Graceful shutdown
        # ----------------------------------------------------

        async def on_aborting() -> None:
            await asyncio.sleep(1)
            await Actor.exit()

        Actor.on(Event.ABORTING, on_aborting)

        # ----------------------------------------------------
        # Read input
        # ----------------------------------------------------

        actor_input = await Actor.get_input() or {}

        raw_start_urls = actor_input.get(
            "start_urls",
            [{"url": DEFAULT_START_URL}],
        )

        start_urls = []

        for item in raw_start_urls:
            if isinstance(item, str):
                start_urls.append(item)

            elif isinstance(item, dict):
                url = item.get("url")

                if url:
                    start_urls.append(url)

        # Remove duplicates.
        start_urls = list(dict.fromkeys(start_urls))

        if not start_urls:
            Actor.log.error(
                "No start URLs supplied. Exiting."
            )
            await Actor.exit()

        Actor.log.info(
            f"Starting scholarship hunt with {len(start_urls)} start URL(s)."
        )

        # ----------------------------------------------------
        # Crawler
        # ----------------------------------------------------

        crawler = BeautifulSoupCrawler(

            # Increase this when you're happy with the results.
            # Start with 50 to keep costs/testing under control.
            max_requests_per_crawl=50,

            request_handler=router,
        )

        # ----------------------------------------------------
        # Run
        # ----------------------------------------------------

        await crawler.run(start_urls)

        Actor.log.info(
            "Scholarship hunt completed successfully."
        )


if __name__ == "__main__":
    asyncio.run(main())
