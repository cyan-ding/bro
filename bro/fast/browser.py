"""One Chrome for the whole session, kept behind the user's windows, with tracker blocking."""

import os
import subprocess
from typing import List, Optional, Tuple

from patchright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

CDP_URL = os.environ.get("BRO_CDP_URL", "http://localhost:9222")
WINDOW = os.environ.get("BRO_WINDOW", "1440,1100")

# Hosts that only serve ads, trackers or analytics. Blocking them removes overlay ads and
# consent-adjacent iframes from the observation and speeds page loads.
BLOCKED_URL_PATTERNS: List[str] = [
    "*doubleclick.net*", "*googlesyndication.com*", "*googleadservices.com*", "*adservice.google.*",
    "*google-analytics.com*", "*googletagmanager.com*", "*googletagservices.com*", "*amazon-adsystem.com*",
    "*adnxs.com*", "*adsrvr.org*", "*rubiconproject.com*", "*pubmatic.com*", "*openx.net*", "*criteo.*",
    "*taboola.com*", "*outbrain.com*", "*scorecardresearch.com*", "*quantserve.com*", "*moatads.com*",
    "*2mdn.net*", "*casalemedia.com*", "*indexww.com*", "*bidswitch.net*", "*smartadserver.com*",
    "*teads.tv*", "*sharethrough.com*", "*33across.com*", "*media.net*", "*yieldmo.com*", "*triplelift.com*",
    "*hotjar.com*", "*mixpanel.com*", "*segment.io*", "*segment.com*", "*fullstory.com*", "*newrelic.com*",
    "*nr-data.net*", "*chartbeat.com*", "*permutive.com*", "*bounceexchange.com*", "*liveperson.net*",
    "*connect.facebook.net*", "*facebook.com/tr*", "*ads.linkedin.com*", "*snap.licdn.com*", "*bat.bing.com*",
    "*.woff", "*.woff2", "*.ttf", "*.otf", "*.mp4", "*.webm", "*.m3u8",
]


def _frontmost_app() -> str:
    try:
        return subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def _activate(app: str) -> None:
    if app and app not in ("Google Chrome", "Chrome"):
        subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], capture_output=True, timeout=5)


async def connect(cdp_url: str = CDP_URL) -> Tuple[Playwright, Optional[Browser], BrowserContext]:
    """Attach to Chrome over CDP, or (BRO_BROWSER=patchright) launch real Chrome through Patchright.

    Patchright's own launch applies its anti-detection patches; a bare --remote-debugging-port
    profile does not, and some sites (Google properties) never finish loading in one. The window
    is launched once and sent behind whatever the user was using; nothing raises it afterwards.
    """
    playwright = await async_playwright().start()
    if os.environ.get("BRO_BROWSER") == "patchright":
        profile = os.environ.get("BRO_PROFILE_DIR", os.path.expanduser("~/tmp/chrome-profile-patchright"))
        previous = _frontmost_app()
        width, height = WINDOW.split(",")
        context = await playwright.chromium.launch_persistent_context(
            profile,
            channel="chrome",
            headless=False,
            no_viewport=True,
            viewport=None,
            locale="en-US",
            reduced_motion="reduce",
            args=[
                f"--window-size={width},{height}",
                "--lang=en-US",
                # An occluded or background tab stops painting: scrolls time out and keys get dropped.
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        )
        _activate(previous)
        return playwright, None, context
    browser = await playwright.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    return playwright, browser, context


async def prepare_page(page: Page) -> None:
    """Block trackers at the network layer and emulate focus so a background tab behaves like a focused one."""
    if getattr(page, "_bro_prepared", False):
        return
    page._bro_prepared = True  # type: ignore[attr-defined]
    try:
        session = await page.context.new_cdp_session(page)
        await session.send("Network.enable")
        await session.send("Network.setBlockedURLs", {"urls": BLOCKED_URL_PATTERNS})
        await session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
    except Exception:
        pass


async def disconnect(playwright: Playwright, browser: Optional[Browser], context: BrowserContext) -> None:
    if browser is None:
        await context.close()
    else:
        await browser.close()
    await playwright.stop()


async def fresh_page(context: BrowserContext) -> Page:
    """Return one tab on about:blank, prepared for the agent, with every other tab closed.

    The existing tab is reused: opening a tab through CDP raises the Chrome window on macOS, so a
    tab is only created when none is left, and the user's app is re-activated right after.
    """
    pages = list(context.pages)
    if pages:
        page = pages[0]
        for other in pages[1:]:
            try:
                await other.close()
            except Exception:
                pass
        await page.goto("about:blank")
    else:
        previous = _frontmost_app()
        page = await context.new_page()
        _activate(previous)
    await prepare_page(page)
    return page
