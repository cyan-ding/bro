"""One recorder for both agents: CDP Page.screencast frames with timestamps, saved as JPEGs plus index.json.

In-process (Bro):  rec = Screencast(out_dir); await rec.attach(context); ...; await rec.stop()
Separate process (browser-use):  python -m bro.bench.compare.screencast --cdp http://127.0.0.1:9333 --out DIR
The CLI form records until it receives SIGTERM.
"""

import argparse
import asyncio
import base64
import signal
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from patchright.async_api import BrowserContext, CDPSession, Page, async_playwright

from .models import ScreencastIndex


class Screencast:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.frames: List[Tuple[float, str]] = []
        self.sessions: List[CDPSession] = []
        self.t0 = time.time()

    async def _watch(self, page: Page) -> None:
        session = await page.context.new_cdp_session(page)

        async def on_frame(event: Dict[str, Any]) -> None:
            name = f"{len(self.frames):06d}.jpg"
            (self.out_dir / name).write_bytes(base64.b64decode(event["data"]))
            self.frames.append((time.time() - self.t0, name))
            try:
                await session.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
            except Exception:
                pass

        session.on("Page.screencastFrame", lambda event: asyncio.ensure_future(on_frame(event)))
        await session.send("Page.startScreencast", {"format": "jpeg", "quality": 70, "maxWidth": 1280, "maxHeight": 980})
        self.sessions.append(session)

    async def attach(self, context: BrowserContext) -> None:
        for page in context.pages:
            await self._watch(page)
        context.on("page", lambda page: asyncio.ensure_future(self._watch(page)))

    async def stop(self) -> None:
        end = time.time() - self.t0
        for session in self.sessions:
            try:
                await session.send("Page.stopScreencast")
            except Exception:
                pass
        index = ScreencastIndex(frames=self.frames, end=end)
        (self.out_dir / "index.json").write_text(index.model_dump_json())


async def record_until_sigterm(cdp_url: str, out_dir: Path) -> None:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.connect_over_cdp(cdp_url)
    recorder = Screencast(out_dir)
    await recorder.attach(browser.contexts[0])
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    await stop.wait()
    await recorder.stop()
    await playwright.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    asyncio.run(record_until_sigterm(args.cdp, Path(args.out)))
