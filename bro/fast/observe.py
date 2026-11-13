"""Compact page observation: interactive elements plus visible text, no screenshot."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from patchright.async_api import Page
from pydantic import BaseModel

from bro.utils.dom_utils import load_js_bundle

_VISIBLE_TEXT_JS = """
(maxChars) => {
    const vh = window.innerHeight, vw = window.innerWidth;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    const out = [];
    let total = 0;
    const skip = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
    while (walker.nextNode()) {
        const node = walker.currentNode;
        const isImg = node.nodeType === 1;
        if (isImg && node.tagName !== "IMG") continue;
        const raw = isImg ? (node.getAttribute("alt") || "") : node.textContent;
        const t = raw.replace(/\\s+/g, " ").trim();
        if (t.length < 2) continue;
        const el = isImg ? node : node.parentElement;
        if (!el || skip.has(el.tagName)) continue;
        const r = el.getBoundingClientRect();
        if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw || r.width === 0 || r.height === 0) continue;
        const cs = window.getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") continue;
        out.push(t);
        total += t.length + 1;
        if (total > maxChars) break;
    }
    return out.join(" | ");
}
"""

_SCROLL_JS = """
() => ({
    y: Math.round(window.scrollY),
    h: Math.round(window.innerHeight),
    total: Math.round(document.documentElement.scrollHeight)
})
"""

_ATTR_ORDER = (
    "type",
    "placeholder",
    "aria-label",
    "role",
    "value",
    "checked",
    "name",
    "alt",
    "title",
    "aria-expanded",
    "href",
)


class Element(BaseModel):
    index: int
    tag: str
    xpath: str
    ref: Optional[int] = None
    iframe_xpath: Optional[str] = None
    attrs: Dict[str, Any] = {}
    text: str = ""
    note: str = ""

    def fingerprint(self) -> str:
        """Identity that survives re-indexing between steps."""
        return f"{self.tag}|{self.text[:40]}|{self.attrs.get('href', '')}|{self.attrs.get('aria-label', '')}"


class Observation(BaseModel):
    url: str
    title: str
    elements: List[Element]
    text: str
    scroll_y: int
    viewport_h: int
    page_h: int

    def element(self, index: int) -> Optional[Element]:
        return next((e for e in self.elements if e.index == index), None)

    def scroll_summary(self) -> str:
        above = self.scroll_y
        below = max(0, self.page_h - self.scroll_y - self.viewport_h)
        return f"{above}px above, {below}px below"


def _short_href(href: str, page_url: str) -> Optional[str]:
    if href.startswith(("#", "javascript:")):
        return None
    origin = urlsplit(page_url)
    target = urlsplit(href)
    if target.netloc == origin.netloc:
        href = target.path + (f"?{target.query}" if target.query else "")
    return href[:40]


def _format_element(el: Element, page_url: str) -> str:
    parts: List[str] = []
    for key in _ATTR_ORDER:
        val = el.attrs.get(key)
        if val in (None, ""):
            continue
        val = str(val)
        if key == "href":
            short = _short_href(val, page_url)
            if short is None:
                continue
            val = short
        if key == "name" and el.text:
            continue
        parts.append(f'{key}="{val}"' if " " in val else f"{key}={val}")
    attrs = (" " + " ".join(parts)) if parts else ""
    note = f" {el.note}" if el.note else ""
    return f"[{el.index}]<{el.tag}{attrs}>{el.text[:80]}{note}"


INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "summary", "option", "label"}
INTERACTIVE_ROLES = {
    "button", "link", "checkbox", "radio", "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "option",
    "combobox", "textbox", "searchbox", "switch", "slider", "spinbutton", "listbox", "treeitem",
}


def _is_real(el: Element) -> bool:
    return el.tag in INTERACTIVE_TAGS or str(el.attrs.get("role", "")).lower() in INTERACTIVE_ROLES


def collapse(elements: List[Element]) -> List[Element]:
    """Fold wrapper divs/spans/imgs into their nearest real interactive ancestor, keeping its text.

    The DOM script flags anything clickable-looking; without a screenshot the model only needs real
    controls, each carrying the text of the wrappers inside it.
    """
    kept: List[Element] = []
    for el in elements:
        if el.iframe_xpath is None:
            ancestor = next(
                (k for k in reversed(kept) if k.iframe_xpath is None and _is_real(k) and el.xpath.startswith(k.xpath + "/")),
                None,
            )
        else:
            ancestor = None
        if _is_real(el):
            kept.append(el)
            continue
        text = el.text or str(el.attrs.get("alt", "")).strip()
        if ancestor is not None:
            if text and text not in ancestor.text:
                ancestor.text = (ancestor.text + " " + text).strip()
            continue
        if text:
            kept.append(el.model_copy(update={"text": text}))
    return kept


def signature(obs: Observation) -> str:
    """Compact fingerprint of what the agent can see; equal before and after an action means it did nothing."""
    body = "|".join(f"{e.tag}:{e.text[:30]}:{e.attrs.get('value', '')}:{e.attrs.get('checked', '')}" for e in obs.elements[:150])
    return f"{obs.url}|{obs.title}|{obs.scroll_y}|{hash(body)}|{hash(obs.text[:600])}"


def format_elements(obs: Observation, max_elements: int = 120) -> str:
    lines = [_format_element(e, obs.url) for e in obs.elements[:max_elements]]
    if len(obs.elements) > max_elements:
        lines.append(f"... {len(obs.elements) - max_elements} more elements below")
    return "\n".join(lines) if lines else "(no interactive elements)"


async def ensure_dom_script(page: Page) -> None:
    injected = await page.evaluate("() => Boolean(window.domTreeInjected)")
    if not injected:
        await page.evaluate(await load_js_bundle())


_LEAN_JS = (Path(__file__).with_name("observe.js")).read_text(encoding="utf-8")


async def observe_lean(page: Page, max_text_chars: int = 1500, max_elements: int = 200) -> Observation:
    """One JS pass over the viewport; elements are addressed by handle (`ref`) instead of XPath."""
    result = await page.evaluate(_LEAN_JS, {"maxTextChars": max_text_chars, "maxElements": max_elements})
    elements = [
        Element(index=int(e["index"]), tag=str(e["tag"]), xpath="", ref=int(e["index"]), attrs=e.get("attrs") or {}, text=e.get("text") or "")
        for e in result["elements"]
    ]
    scroll = result["scroll"]
    return Observation(
        url=result["url"],
        title=result["title"],
        elements=elements,
        text=result["text"],
        scroll_y=int(scroll["y"]),
        viewport_h=int(scroll["h"]),
        page_h=int(scroll["total"]),
    )


async def observe(page: Page, max_text_chars: int = 1500) -> Observation:
    """Build a compact observation of the current viewport."""
    await ensure_dom_script(page)
    result = await page.evaluate(
        "(args) => window.buildDomTree(args)",
        {"doHighlightElements": False, "overlapThreshold": 0.7, "indexByPosition": True},
    )
    raw: List[Dict[str, Any]] = result.get("highlightedElementsSerialized", [])
    elements = [
        Element(
            index=int(e["index"]),
            tag=str(e.get("tag", "div")),
            xpath=str(e.get("xpath", "")),
            iframe_xpath=e.get("iframe_xpath"),
            attrs=e.get("attrs") or {},
            text=(e.get("text") or "").strip(),
        )
        for e in raw
        if e.get("index") is not None
    ]
    elements = collapse(elements)
    text = await page.evaluate(_VISIBLE_TEXT_JS, max_text_chars)
    scroll = await page.evaluate(_SCROLL_JS)
    return Observation(
        url=page.url,
        title=await page.title(),
        elements=elements,
        text=text,
        scroll_y=int(scroll["y"]),
        viewport_h=int(scroll["h"]),
        page_h=int(scroll["total"]),
    )
