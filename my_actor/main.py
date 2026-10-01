"""Main entry point for Master Scholarship Hunter."""

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

        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=100,
            request_handler=router,
        )

        await crawler.run(start_urls)

        Actor.log.info("Master Scholarship Hunter finished successfully.")


if __name__ == "__main__":
    asyncio.run(main())
