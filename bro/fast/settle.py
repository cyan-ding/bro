"""Wait for a page to go quiet after an action, without fixed sleeps."""

import asyncio

from patchright.async_api import Page

_INSTALL_OBSERVER_JS = """
() => {
    if (window.__broMut === undefined) {
        window.__broMut = 0;
        new MutationObserver(() => { window.__broMut++; })
            .observe(document.documentElement, {subtree: true, childList: true, attributes: true, characterData: true});
    }
    return window.__broMut;
}
"""


async def settle(page: Page, quiet_ms: int = 150, max_ms: int = 1500, poll_ms: int = 50) -> None:
    """Return once no DOM mutations happened for `quiet_ms`, or after `max_ms`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_ms / 1000
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=max_ms)
    except Exception:
        return
    last_count = -1
    quiet_since = loop.time()
    while loop.time() < deadline:
        try:
            count = await page.evaluate(_INSTALL_OBSERVER_JS)
        except Exception:
            # Execution context destroyed by navigation: wait for the new document.
            await asyncio.sleep(poll_ms / 1000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=max_ms)
            except Exception:
                return
            last_count = -1
            continue
        now = loop.time()
        if count != last_count:
            last_count = count
            quiet_since = now
        elif (now - quiet_since) * 1000 >= quiet_ms:
            return
        await asyncio.sleep(poll_ms / 1000)
