"""Connect to the user's Chrome over CDP and hand out a page for the agent."""

import os
from typing import Tuple

from patchright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

CDP_URL = os.environ.get("BRO_CDP_URL", "http://localhost:9222")


async def connect(cdp_url: str = CDP_URL) -> Tuple[Playwright, Browser, BrowserContext]:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    return playwright, browser, context


async def fresh_page(context: BrowserContext) -> Page:
    """Close every tab but one and return it on about:blank."""
    page = await context.new_page()
    for other in list(context.pages):
        if other is not page:
            try:
                await other.close()
            except Exception:
                pass
    return page
