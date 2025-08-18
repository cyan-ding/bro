"""
HTML ingestion and normalization utilities using BeautifulSoup.

Provides helpers to sanitize noisy markup and extract semantic text from HTML or
from a fetched URL. The normalization follows a conservative subset of WHATWG
semantics:

- Keep only semantic text blocks: p, table, pre, blockquote, ul, ol, dl
- Remove/unwrap layout, interactive, metadata, and foreign elements
- Collapse whitespace and flatten inline trees; no loose text nodes outside <p>
- Prefer <main><article> when available; otherwise <article>, then <main>, then
  <body>
- Remove common chrome: nav/header/footer/aside/forms and ARIA role equivalents
- Apply site-specific rules (e.g., Wikipedia) to reduce noise

How it fits: Feeds normalized text into the RAG pipeline before chunking/embedding.

@file purpose: Defines text extraction helpers for RAG ingestion
"""

# @file purpose: Defines text extraction helpers for RAG ingestion

from __future__ import annotations

import re
from typing import List, Optional, Sequence
from urllib.parse import urljoin

from bs4 import (
    BeautifulSoup,
    Comment,
    NavigableString,
    Tag,
)
from playwright.async_api import Page


def _select_content_root(soup: BeautifulSoup) -> Tag:
    """Choose a content root favoring main > article, then article, main, body.

    Args:
        soup: Parsed BeautifulSoup document.

    Returns:
        Tag that represents the best content root; falls back to document body.
    """
    main_tag = soup.find("main")
    if main_tag is not None:
        article_in_main = main_tag.find("article")
        if article_in_main is not None:
            return article_in_main
    article_tag = soup.find("article")
    if article_tag is not None:
        return article_tag
    if main_tag is not None:
        return main_tag
    return soup.body or soup


def _remove_comments_and_noncontent(root: Tag) -> None:
    """Remove comments, scripts, styles, and non-content chrome elements."""

    # Remove comments
    for c in root.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()  # safer for strings

    # Remove obvious non-content tags
    blacklist_tags: Sequence[str] = (
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "iframe",
        "object",
        "embed",
        "form",
        "input",
        "button",
        "select",
        "label",
        "nav",
        "aside",
        "template",
        "menu",
        "dialog",
        # maybe reconsider: "sup"
    )
    for t in root.find_all(blacklist_tags):
        t.decompose()

    # Remove by ARIA role when present
    roles_to_remove = {
        "navigation",
        "banner",
        "complementary",
        "contentinfo",
        "search",
        "menu",
        "menubar",
        "dialog",
        "button",
        "form",
        "toolbar",
        "tablist",
        "tab",
        "alert",
        "status",
    }
    for t in root.find_all(attrs={"role": True}):
        try:
            role_val = t.attrs.get("role", "")
            role_tokens = {
                r.strip().lower() for r in str(role_val).split() if r.strip()
            }
            if role_tokens & roles_to_remove:
                t.decompose()
        except (AttributeError, TypeError, ValueError):
            continue


def _apply_wikipedia_rules(root: Tag, *, url: Optional[str]) -> None:
    """Apply targeted cleanups for en.wikipedia.org pages.

    Args:
        root: Content root to clean up.
        url: Source URL if available. Rules apply only when URL matches.
    """
    if not url or not re.match(r"^https?://en\.wikipedia\.org/wiki/", url):
        return

    # Remove classes/ids known to be non-content
    class_based_removals = {
        "hatnote",  # Remove "meta" information about the Wikipedia article itself. See https://en.wikipedia.org/wiki/Wikipedia:Hatnote.
        "thumb",  # Remove figures.
        "navbox",  # Remove the navigation boxes at the bottom of the page.
        "printfooter",  # Remove the message "Retrieved from $url".
        "mw-jump-link",  # Remove "Jump to content" link.
        "mw-editsection",  # Remove "[edit]" links.
        "mw-ui-button",  # Remove UI buttons.
        "wb-langlinks-edit",  # Remove "Edit links" link.
        "mwe-math-fallback-image-display",  # Remove math fallback images.
        "mwe-math-fallback-image-inline",  # Remove math fallback images.
    }

    # for el in list(root.find_all(True)):
    #     classes = set(el.get("class", []))
    #     el_id = el.get("id", "")
    #     tag_name = el.name

    #     if tag_name == "ol" and set(["references", "citations"]) & classes:
    #         # Remove section containing list of references/citations.
    #         el.decompose()
    #         continue
    #     if tag_name == "table" and "sidebar" in classes:
    #         # Remove sidebar, which sometimes contains useful facts but often just contains "adjacent" information and links.
    #         el.decompose()
    #         continue
    #     if classes & class_based_removals:
    #         # Remove elements with classes in class_based_removals (see above for details).
    #         print("Removing element:", tag_name, "classes=", classes)
    #         el.decompose()
    #         continue
    #     if el_id == "siteSub":
    #         # Remove the message "From Wikipedia, the free encyclopedia".
    #         el.decompose()
    #         continue

    # if tag_name == "sup" and "reference" in classes:
    #     # Remove numbered references around square brackets within body text.
    #     el.decompose()
    #     continue

    # Remove sections by heading (e.g., External links, See also)
    forbidden_sections = {
        "sources",
        "further reading",
        "external links",
        "see also",
    }
    for h2 in list(root.find_all("h2")):
        heading_text = (
            h2.get_text(" ", strip=True).replace("[edit]", "").strip().lower()
        )
        if any(fs in heading_text for fs in forbidden_sections):
            nxt = h2.find_next_sibling()
            h2.decompose()
            while nxt is not None:
                if nxt.name == "h2":
                    break
                to_remove = nxt
                nxt = nxt.find_next_sibling()
                to_remove.decompose()


def _remove_hidden_and_noise(root: Tag) -> None:
    """Remove hidden elements and common boilerplate/noise."""
    for el in list(root.find_all(True)):
        try:
            attrs = el.attrs
            # Hidden semantics
            if "hidden" in attrs:
                el.decompose()
                continue
            if str(attrs.get("aria-hidden", "")).lower() == "true":
                el.decompose()
                continue
            # Inline styles
            style = str(attrs.get("style", "")).lower()
            if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", style):
                el.decompose()
                continue
            # IDs and classes
            id_or_classes = " ".join(
                [
                    str(attrs.get("id", "")),
                    " ".join(attrs.get("class", []) or []),
                ]
            ).lower()
            if id_or_classes and re.search(
                r"(?:^|[-_\s])(ad|advert|promo|sponsored|breadcrumb|pagination|share|social|subscribe|newsletter|related|tags|comments)(?:$|[-_\s])",
                id_or_classes,
            ):
                el.decompose()
                continue
        except (AttributeError, TypeError, ValueError):
            continue


def _replace_anchor_with_text(
    el: Tag, *, include_links: bool, base_url: Optional[str]
) -> None:
    """Replace <a> elements with plain text, optionally appending URLs.

    Args:
        el: Container to process.
        include_links: If True, append " (URL)" after link text.
        base_url: Base URL used to resolve relative links.
    """
    for a in el.find_all("a"):
        link_text = a.get_text(" ", strip=True)
        href = (a.get("href", "") or "").strip()
        replacement: str
        if include_links and href:
            # Skip non-content schemes and fragment-only links
            if href.startswith(("javascript:", "mailto:", "https://", "http://", "#")):
                replacement = link_text
            else:
                abs_href = urljoin(base_url, href) if base_url else href
                replacement = f"{link_text} ({abs_href})" if link_text else abs_href
        else:
            replacement = link_text
        a.replace_with(NavigableString(replacement))


def _normalize_inline_elements(root: Tag) -> None:
    """Normalize inline elements to preserve text flow.

    Converts inline formatting elements like <strong>, <em>, <span>, etc.
    to plain text while preserving their content, preventing line breaks.
    """
    # Common inline elements that should not break text flow
    inline_tags = {
        "strong",
        "b",
        "em",
        "i",
        "u",
        "mark",
        "small",
        "del",
        "ins",
        "sub",
        "sup",
        "span",
        "cite",
        "dfn",
        "abbr",
        "acronym",
        "kbd",
        "samp",
        "var",
        "time",
        "data",
        "q",
        "s",
        "strike",
    }

    for tag in root.find_all(inline_tags):
        # Get the text content and replace the tag with it
        text_content = tag.get_text(" ", strip=True)
        if text_content:
            tag.replace_with(NavigableString(text_content))
        else:
            # If no text content, just remove the tag
            tag.decompose()


def _collect_semantic_blocks(root: Tag) -> List[Tag]:
    """Collect semantic block elements in document order.

    Only keeps: headings h1-h6, p, table, pre, blockquote, ul, ol, dl, figure, hr.
    Avoids duplicates by excluding elements that have an allowed ancestor.
    """
    allowed = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "table",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "dl",
        "figure",
        "hr",
        "code",
    }
    blocks: List[Tag] = []
    for element in root.find_all(list(allowed)):
        if not element.find_parent(list(allowed)):
            blocks.append(element)
    return blocks


def _text_from_block(el: Tag, *, include_links: bool, base_url: Optional[str]) -> str:
    """Render a semantic block to normalized text.

    - p: inline text with preserved flow (no line breaks)
    - pre: preserve text
    - code: preserve text with whitespace normalization
    - blockquote: "> " prefix per line
    - ul/ol: list items, one per line ("- " or "1. ")
    - dl: term: definition
    - table: markdown-like with optional header and caption
    - headings: markdown-style # prefixes
    - figure: caption and optional image alt/src
    - hr: ---
    """
    name = el.name
    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(name[1])
        text = " ".join(list(el.stripped_strings))
        return f"{'#' * level} {text}".strip()
    if name in {"pre", "code"}:
        # output_lines = []
        # current_line = ""
        # text = el.get_text("\n", strip=False)
        # lines = text.splitlines()
        # for line in lines:
        #     if line.isspace() and len(line) > 2:
        #         # if line is multiple spaces (indent), append previous buffer and start new line with indent
        #         output_lines.append(current_line.rstrip())
        #         current_line = line

        #     else:
        #         # if the line is regular text or a space, append to current line
        #         current_line += line
        # output_lines.append(current_line)
        # return "\n".join(output_lines)

        text = el.get_text(separator="", strip=False)
        return text.strip("\n")
    if name == "blockquote":
        text = " ".join(list(el.stripped_strings))
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return "\n".join([f"> {ln.strip()}" for ln in lines])
    if name in {"ul", "ol"}:
        is_ol = name == "ol"
        items: List[str] = []
        idx = 1
        for li in el.find_all("li", recursive=False):
            item_text = " ".join(list(li.stripped_strings))
            if not item_text:
                continue
            prefix = f"{idx}. " if is_ol else "- "
            items.append(prefix + item_text)
            idx += 1
        return "\n".join(items)
    if name == "dl":
        lines: List[str] = []
        current_term: Optional[str] = None
        for child in el.find_all(["dt", "dd"], recursive=False):
            if child.name == "dt":
                current_term = " ".join(list(child.stripped_strings))
            elif child.name == "dd" and current_term:
                definition = " ".join(list(child.stripped_strings))
                lines.append(f"{current_term}: {definition}")
        return "\n".join(lines)
    if name == "table":
        caption = el.find("caption")
        caption_text = caption.get_text(" ", strip=True) if caption else ""

        # Gather rows in thead, tbody, tfoot order
        def rows_from(section: Optional[Tag]) -> List[List[str]]:
            if section is None:
                return []
            rows: List[List[str]] = []
            for tr in section.find_all("tr", recursive=False):
                cells = tr.find_all(["th", "td"], recursive=False)
                cell_texts = [" ".join(list(c.stripped_strings)) for c in cells]
                rows.append(cell_texts)
            # Drop completely empty rows
            return [r for r in rows if any(cell.strip() for cell in r)]

        thead = el.find("thead", recursive=False)
        tbody = el.find("tbody", recursive=False) or el
        tfoot = el.find("tfoot", recursive=False)

        header_rows = rows_from(thead)
        body_rows = rows_from(tbody)
        footer_rows = rows_from(tfoot)
        # if theres no header but theres body, try to make a header from the first row
        if not header_rows and body_rows:
            first_tr = el.find("tr", recursive=False)
            if first_tr is not None:
                first_cells = first_tr.find_all(["th", "td"], recursive=False)
                if first_cells and all(c.name == "th" for c in first_cells):
                    header_rows = [
                        ["".join(list(c.stripped_strings)) for c in first_cells]
                    ]
                    body_rows = body_rows[1:]

        lines: List[str] = []
        if caption_text:
            lines.append(f"Table: {caption_text}")
        if header_rows:
            header = " | ".join(header_rows[0])
            sep = " | ".join("---" for _ in header_rows[0])
            lines += [header, sep]
        lines += [" | ".join(r) for r in (body_rows + footer_rows)]
        return "\n".join(lines).strip()
    if name == "figure":
        caption = el.find("figcaption")
        caption_text = caption.get_text(" ", strip=True) if caption else ""
        img = el.find("img")
        parts: List[str] = []
        if caption_text:
            parts.append(f"Figure: {caption_text}")
        if img:
            alt = (img.get("alt", "") or "").strip()
            src = (img.get("src", "") or "").strip()
            if alt:
                parts.append(f"Image: {alt}")
            if include_links and src:
                parts.append(f"(src: {urljoin(base_url, src) if base_url else src})")
        return " ".join(parts).strip()
    if name == "hr":
        return "---"

    # Default: paragraph-like
    # For paragraphs and other text blocks, preserve inline flow
    text = el.get_text(" ", strip=True)  # Use space separator instead of newline
    # Clean up excessive whitespace while preserving word boundaries
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Promote paragraph-like divs to paragraphs before link replacement and block collection
def _promote_paragraph_like_divs(root: Tag) -> None:
    """Promote divs that are primarily text into paragraphs.

    Converts a <div> into a <p> when it has no direct block children and
    carries enough text to look like a paragraph.
    """
    block_tags = {
        "p",
        "table",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "dl",
        "section",
        "article",
    }
    for div in list(root.find_all("div")):
        has_block_children = any(div.find_all(list(block_tags), recursive=False))
        texty = " ".join(list(div.stripped_strings))
        if not has_block_children and len(texty.split()) >= 5:
            div.name = "p"


def extract_text(
    html: str, *, include_links: bool = False, url: Optional[str] = None
) -> str:
    """Extract normalized text content from an HTML document.

    Args:
        html: Raw HTML string.
        include_links: Whether to append URLs after link text.
        url: Optional source URL for site-specific rules.

    Returns:
        Normalized plain text with semantic structure preserved by newlines.
    """
    if html is None or html.strip() == "":
        return ""

    soup = BeautifulSoup(html, "html.parser")
    root = _select_content_root(soup)

    _remove_comments_and_noncontent(root)
    _remove_hidden_and_noise(root)
    _apply_wikipedia_rules(root, url=url)
    _promote_paragraph_like_divs(root)
    _replace_anchor_with_text(root, include_links=include_links, base_url=url)
    _normalize_inline_elements(root)

    blocks = _collect_semantic_blocks(root)
    texts: List[str] = []
    for b in blocks:
        block_text = _text_from_block(b, include_links=include_links, base_url=url)
        if block_text.strip():
            texts.append(block_text.strip())

    return "\n\n".join(texts).strip()


async def fetch_and_extract(page: Page, *, include_links: bool = False) -> str:
    """Extract normalized text from a Playwright asynchronous `Page`.

    This awaits `page.content()` and uses `page.url` if available.

    Args:
        page: A `playwright.async_api.Page`-like object exposing async `.content()` and `.url`.
        include_links: Whether to append URLs after link text.

    Returns:
        Normalized text extracted from the page, or an empty string on error.
    """
    try:
        html: str = await page.content()
        page_url: Optional[str] = getattr(page, "url", None)
        return extract_text(html, include_links=include_links, url=page_url)
    except Exception:
        return ""


async def demo_fetch_random_wikipedia(include_links: bool = False) -> None:
    """Quick demo: navigate to a random Wikipedia page and print extracted text.

    Args:
        include_links: Whether to append resolved URLs next to link text.
    """
    from browser.use_cdp import use_cdp
    from playwright.async_api import async_playwright

    await use_cdp()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # List contexts (Chrome profiles)
        contexts = browser.contexts
        if contexts:
            context = contexts[0]  # Use existing profile
        else:
            context = await browser.new_context()  # Or create new

        page = await context.new_page()
        await page.goto(
            "https://blog.wilsonl.in/search-engine/#normalization",
            wait_until="domcontentloaded",
        )
        text = await fetch_and_extract(page, include_links=include_links)
        with open("extracted_wikipedia.txt", "w", encoding="utf-8") as f:
            f.write(text)
        await browser.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_fetch_random_wikipedia(include_links=False))
