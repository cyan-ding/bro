"""Connect to the user's Chrome over CDP and hand out a page for the agent."""

import os
from typing import Optional, Tuple

from patchright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

CDP_URL = os.environ.get("BRO_CDP_URL", "http://localhost:9222")


async def connect(cdp_url: str = CDP_URL) -> Tuple[Playwright, Optional[Browser], BrowserContext]:
    """Attach to Chrome over CDP, or (BRO_BROWSER=patchright) launch real Chrome through Patchright.

    Patchright's own launch applies its anti-detection patches; a bare --remote-debugging-port
    profile does not, and some sites (Google properties) never finish loading in one.
    """
    playwright = await async_playwright().start()
    if os.environ.get("BRO_BROWSER") == "patchright":
        profile = os.environ.get("BRO_PROFILE_DIR", os.path.expanduser("~/tmp/chrome-profile-patchright"))
        context = await playwright.chromium.launch_persistent_context(
            profile, channel="chrome", headless=False, no_viewport=True, viewport=None
        )
        return playwright, None, context
    browser = await playwright.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    return playwright, browser, context


async def disconnect(playwright: Playwright, browser: Optional[Browser], context: BrowserContext) -> None:
    if browser is None:
        await context.close()
    else:
        await browser.close()
    await playwright.stop()


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
