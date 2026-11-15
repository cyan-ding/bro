"""One Chrome for the whole session, kept behind the user's windows, with tracker blocking."""

import asyncio
import ctypes
import os
import re
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


FRONTMOST_SCRIPT = """tell application "System Events"
set p to first process whose frontmost is true
return (name of p) & "|" & (unix id of p as text)
end tell"""

AGENT_CHROME_PID = 0
FOCUS_GUARD = os.environ.get("BRO_FOCUS_GUARD", "1") != "0"

try:
    _cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    _cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
    _cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int, ctypes.c_uint32]
    _cg.CGEventSourceFlagsState.restype = ctypes.c_uint64
    _cg.CGEventSourceFlagsState.argtypes = [ctypes.c_int]
except OSError:
    _cg = None


def _frontmost() -> Tuple[str, int]:
    """Name and PID of the frontmost app: lsappinfo (about 10 ms), falling back to System Events."""
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=2).stdout.strip()
        info = subprocess.run(["lsappinfo", "info", "-only", "pid", "-only", "name", asn], capture_output=True, text=True, timeout=2).stdout
        pid = re.search(r"pid\s*=\s*(\d+)", info)
        name = re.search(r'"([^"]+)"', info)
        if pid and name:
            return name.group(1), int(pid.group(1))
    except Exception:
        pass
    try:
        out = subprocess.run(["osascript", "-e", FRONTMOST_SCRIPT], capture_output=True, text=True, timeout=5).stdout.strip()
        name, _, pid = out.rpartition("|")
        return name, int(pid)
    except Exception:
        return "", 0


def _frontmost_app() -> str:
    return _frontmost()[0]


def _human_switched(window_s: float = 1.5) -> bool:
    """True when a person plausibly caused the current app switch: any hardware input in the last moment.

    Covers clicks, keys, cmd-tab (modifier flags), trackpad swipes (gestures) and scrolling.
    """
    if _cg is None:
        return False
    recent = _cg.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF) < window_s  # any input
    flags = _cg.CGEventSourceSecondsSinceLastEventType(1, 12) < window_s  # modifier pressed
    gesture = _cg.CGEventSourceSecondsSinceLastEventType(1, 29) < window_s  # trackpad gesture
    scroll = _cg.CGEventSourceSecondsSinceLastEventType(1, 22) < window_s
    cmd_held = bool(_cg.CGEventSourceFlagsState(1) & 0x100000)
    return recent or flags or gesture or scroll or cmd_held


def _chrome_user_agent() -> str:
    """The user-agent string the installed Chrome sends when it has a window (major version only)."""
    try:
        out = subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"], capture_output=True, text=True, timeout=5).stdout
        major = re.search(r"(\d+)\.", out).group(1)
    except Exception:
        major = "140"
    return f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"


def _chrome_pid(profile: str) -> int:
    """PID of the Chrome browser process launched on `profile` (not its helpers)."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return 0
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if f"--user-data-dir={profile}" in cmd and "/Google Chrome " in cmd and "Helper" not in cmd:
            return int(pid)
    return 0


class FocusWatch:
    """Brackets one agent operation: if the agent's Chrome took the front during it, give focus back.

    `start()` samples the frontmost app before the operation; `check(what)` after it. A switch to the
    agent's Chrome with no human input in the last second is the agent's doing: the previous app is
    re-activated and a line naming the operation is returned for the step log. Anything else (the
    user clicking or cmd-tabbing into Chrome) is left alone. Costs about 20 ms per operation.
    """

    def __init__(self) -> None:
        self.before: Tuple[str, int] = ("", 0)

    async def start(self) -> None:
        if FOCUS_GUARD and AGENT_CHROME_PID:
            self.before = await asyncio.to_thread(_frontmost)

    async def check(self, what: str) -> Optional[str]:
        if not (FOCUS_GUARD and AGENT_CHROME_PID) or self.before[1] == AGENT_CHROME_PID or self.before[0] in ("Google Chrome", "Chrome", ""):
            return None  # the user was already in a Chrome (or unknown): nothing sensible to return focus to
        name, pid = await asyncio.to_thread(_frontmost)
        if pid != AGENT_CHROME_PID:
            return None
        if _human_switched():
            return f"{what} coincided with Chrome coming to the front (left alone: recent human input)"
        await asyncio.to_thread(_activate, self.before[0])
        return f"{what} raised Chrome; focus returned to {self.before[0]}"


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
        headless = os.environ.get("BRO_HEADLESS") == "1"
        default_profile = "~/tmp/chrome-profile-patchright-headless" if headless else "~/tmp/chrome-profile-patchright"
        profile = os.environ.get("BRO_PROFILE_DIR", os.path.expanduser(default_profile))
        previous = _frontmost_app()
        width, height = WINDOW.split(",")
        args = [
            f"--window-size={width},{height}",
            "--lang=en-US",
            # An occluded or background tab stops painting: scrolls time out and keys get dropped.
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
        ]
        if headless:
            # No window at all, so nothing can take focus. Chrome's own UA says "HeadlessChrome"; use the normal one.
            args += ["--headless=new", f"--user-agent={_chrome_user_agent()}"]
        context = await playwright.chromium.launch_persistent_context(
            profile,
            channel="chrome",
            headless=headless,
            no_viewport=True,
            viewport=None,
            locale="en-US",
            reduced_motion="reduce",
            args=args,
        )
        if not headless:
            _activate(previous)
            global AGENT_CHROME_PID
            AGENT_CHROME_PID = _chrome_pid(profile)
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
    watch = FocusWatch()
    await watch.start()
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
    note = await watch.check("tab reset")
    if note:
        print(note)
    return page
