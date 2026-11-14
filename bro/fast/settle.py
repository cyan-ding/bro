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


class NetworkTracker:
    """Counts in-flight requests on a page; long-polls (older than 1.5 s) are ignored."""

    def __init__(self, page: Page) -> None:
        self._started: dict = {}
        page.on("request", self._start)
        page.on("requestfinished", self._end)
        page.on("requestfailed", self._end)

    def _start(self, request) -> None:
        if request.resource_type in ("websocket", "eventsource", "media", "ping", "manifest"):
            return
        self._started[request] = asyncio.get_event_loop().time()

    def _end(self, request) -> None:
        self._started.pop(request, None)

    def busy(self) -> bool:
        now = asyncio.get_event_loop().time()
        return any(now - t < 1.5 for t in self._started.values())


def track_network(page: Page) -> NetworkTracker:
    tracker = getattr(page, "_bro_network", None)
    if tracker is None:
        tracker = NetworkTracker(page)
        page._bro_network = tracker  # type: ignore[attr-defined]
    return tracker


async def settle(page: Page, quiet_ms: int = 80, max_ms: int = 800, poll_ms: int = 40) -> None:
    """Return once the DOM has been quiet for `quiet_ms` and no short request is in flight, or after `max_ms`.

    Never a fixed sleep: after a click on a static page this returns in about `quiet_ms`.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_ms / 1000
    network = getattr(page, "_bro_network", None)
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
        if count != last_count or (network is not None and network.busy()):
            last_count = count
            quiet_since = now
        elif (now - quiet_since) * 1000 >= quiet_ms:
            return
        await asyncio.sleep(poll_ms / 1000)
