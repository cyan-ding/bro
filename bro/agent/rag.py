import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from browser.use_cdp import use_cdp
from bs4 import BeautifulSoup
from bs4.element import Comment
from markdownify import markdownify as md
from playwright.async_api import async_playwright


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]
    start_idx: int
    end_idx: int


class MarkdownifyRAGPipeline:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def _remove_comments_and_noncontent(self, root: BeautifulSoup) -> None:
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

        # Remove elements with display:none in style attribute
        for element in root.find_all(style=True):
            if re.search(r"display\s*:\s*none", element["style"], re.IGNORECASE):
                element.decompose()

        # Remove elements with CSS classes that might be hidden
        # (you'd need to know the specific classes)
        for element in root.find_all(class_=["hidden", "invisible"]):
            element.decompose()

        # Remove elements with "dropdown" in any part of the class name
        for element in root.find_all(
            class_=lambda c: c
            and any(
                "dropdown" in cls.lower() for cls in (c if isinstance(c, list) else [c])
            )
        ):
            element.decompose()

    def remove_unwanted_sections(self, text: str) -> str:
        """Remove unwanted sections like references, citations, sources, etc."""
        # Remove Wikipedia-style citation links like [[184]](#cite_note-187) - good
        text = re.sub(r"\[\[\d+\]\]\(#cite_note[^)]*\)", "", text)

        # # Remove Wikipedia edit links like [edit](/w/index.php?title=...&action=edit&section=25 "Edit section: ...")
        text = re.sub(r"\[edit\]\([^)]*\)", "", text)

        # Remove additional edit section links like [&action=edit&section=1 "Edit section: History")]
        text = re.sub(r"\[&action=edit&section=[^\]]*\]", "", text)

        # Remove markdown images like ![Wikipedia](/static/images/mobile/copyright/wikipedia-wordmark-en.svg) - good
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)

        # Convert markdown links to plain text like [Apache web server](/wiki/Apache_webserver "Apache webserver") -> Apache web server
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

        text = re.sub(r"\n{3,}", "\n", text)
        # Define section patterns that should be removed (case-insensitive)
        unwanted_sections = [
            r"references?",
            r"citations?",
            r"sources?",
            r"bibliography",
            r"further reading",
            r"external links?",
            r"see also",
            r"notes?",
            r"footnotes?",
            r"endnotes?",
            r"works cited",
            r"literature cited",
            r"additional sources?",
            r"related links?",
            r"useful links?",
        ]

        # Create a pattern that matches any of these section headers
        # Match headers at any level (# to ######) followed by the unwanted section names
        section_pattern = r"^(#{1,6})\s*(" + "|".join(unwanted_sections) + r")\s*$"

        lines = text.split("\n")
        filtered_lines = []
        skip_section = False
        current_section_level = 0

        for line in lines:
            line_stripped = line.strip()

            # Check if this line is a header
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line_stripped)

            if header_match:
                header_level = len(header_match.group(1))

                # Check if this is an unwanted section header
                if re.match(section_pattern, line_stripped, re.IGNORECASE):
                    skip_section = True
                    current_section_level = header_level
                    continue

                # If we're in a skip section and encounter a header at same or higher level, stop skipping
                elif skip_section and header_level <= current_section_level:
                    skip_section = False
                    current_section_level = 0

            # If we're not skipping this section, add the line
            if not skip_section:
                filtered_lines.append(line)

        return "\n".join(filtered_lines)

    def html_to_markdown(self, html: str) -> str:
        """Convert HTML to markdown using markdownify, removing unwanted sections"""
        # fallback using beautifulsoup to strip script tags
        soup = BeautifulSoup(html, "html.parser")
        self._remove_comments_and_noncontent(soup)
        html = str(soup)

        normalized_html = md(
            html,
            heading_style="ATX",  # Use # headers
            bullets="-",  # Use - for bullets
            escape_misc=False,  # Don't escape special chars
        )

        return self.remove_unwanted_sections(normalized_html)

    async def extract_headers(self, text: str) -> List[Dict[str, Any]]:
        """Extract header hierarchy for metadata"""
        headers = []
        lines = text.split("\n")
        char_pos = 0

        for i, line in enumerate(lines):
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                headers.append(
                    {"level": level, "title": title, "line": i, "char_pos": char_pos}
                )
            char_pos += len(line) + 1

        return headers

    async def semantic_chunking(self, text: str) -> List[Chunk]:
        """Create semantically meaningful chunks"""
        chunks = []
        headers = await self.extract_headers(text)
        paragraphs = re.split(r"\n\s*\n", text)

        current_chunk = ""
        current_start = 0
        current_metadata = {"headers": []}

        char_pos = 0
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check if this paragraph is a header
            header_match = re.match(r"^#{1,6}\s+", para)
            if header_match:
                # If we have content, save current chunk
                if current_chunk and len(current_chunk.strip()) >= self.min_chunk_size:
                    chunks.append(
                        Chunk(
                            content=current_chunk.strip(),
                            metadata=current_metadata.copy(),
                            start_idx=current_start,
                            end_idx=char_pos,
                        )
                    )

                # Start new chunk with this header
                current_chunk = para
                current_start = char_pos

                # Update metadata with current header context
                level = len(header_match.group(0).strip())
                title = para[level + 1 :].strip()
                current_metadata = {
                    "headers": await self._get_header_context(headers, char_pos, level)
                }
                current_metadata["headers"].append({"level": level, "title": title})

            else:
                # Regular paragraph - add to current chunk
                if current_chunk:
                    test_chunk = current_chunk + "\n\n" + para
                else:
                    test_chunk = para

                # If adding this paragraph exceeds chunk size, finalize current chunk
                if len(test_chunk) > self.chunk_size and current_chunk:
                    chunks.append(
                        Chunk(
                            content=current_chunk.strip(),
                            metadata=current_metadata.copy(),
                            start_idx=current_start,
                            end_idx=char_pos,
                        )
                    )

                    # Start new chunk with overlap
                    overlap_text = await self._get_overlap(current_chunk)
                    current_chunk = overlap_text + para if overlap_text else para
                    current_start = (
                        char_pos - len(overlap_text) if overlap_text else char_pos
                    )
                else:
                    current_chunk = test_chunk

            char_pos += len(para) + 2  # +2 for \n\n

        # Add final chunk
        if current_chunk and len(current_chunk.strip()) >= self.min_chunk_size:
            chunks.append(
                Chunk(
                    content=current_chunk.strip(),
                    metadata=current_metadata,
                    start_idx=current_start,
                    end_idx=char_pos,
                )
            )

        return chunks

    async def _get_header_context(
        self, headers: List[Dict], char_pos: int, current_level: int
    ) -> List[Dict]:
        """Get relevant parent headers for context"""
        context = []
        for header in reversed(headers):
            if header["char_pos"] < char_pos and header["level"] < current_level:
                context.insert(0, header)
                current_level = header["level"]
        return context

    async def _get_overlap(self, text: str) -> str:
        """Extract overlap text from end of chunk"""
        if len(text) <= self.chunk_overlap:
            return text

        # Try to break at sentence boundary
        overlap_start = len(text) - self.chunk_overlap
        sentences = re.split(r"[.!?]+\s+", text[overlap_start:])

        if len(sentences) > 1:
            return (
                sentences[-2] + ". " + sentences[-1]
                if len(sentences[-2]) > 20
                else sentences[-1]
            )

        return text[-self.chunk_overlap :]

    async def process(self, html_content: str) -> List[Chunk]:
        """Full pipeline: HTML -> Markdown -> Normalize -> Chunk"""

        # Step 1: Convert HTML to Markdown
        markdown = self.html_to_markdown(html_content)

        # Step 2: Create semantic chunks
        chunks = await self.semantic_chunking(markdown)

        return chunks


async def main():
    pipeline = MarkdownifyRAGPipeline(
        chunk_size=800, chunk_overlap=150, min_chunk_size=50
    )

    await use_cdp()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # List contexts (Chrome profiles)
        contexts = browser.contexts
        if contexts:
            browser_context = contexts[0]  # Use existing profile
        else:
            browser_context = await browser.new_context()  # Or create new
        # Open a new tab
        page = (
            browser_context.pages[0]
            if browser_context.pages
            else await browser_context.new_page()
        )
        await page.goto("https://blog.wilsonl.in/search-engine/#normalization")
        html = await page.content()
        md = pipeline.html_to_markdown(html)
        print(md)


# Usage example
if __name__ == "__main__":
    asyncio.run(main())

    # # Example HTML content
    # html = """
    # <html>
    #     <body>
    #         <h1>Introduction to RAG</h1>
    #         <p>Retrieval-Augmented Generation (RAG) is a powerful technique...</p>

    #         <h2>Key Components</h2>
    #         <p>RAG systems typically consist of:</p>
    #         <ul>
    #             <li>A retrieval system</li>
    #             <li>A generative model</li>
    #             <li>A vector database</li>
    #         </ul>

    #         <h3>Vector Databases</h3>
    #         <p>Vector databases store embeddings of your documents...</p>
    #     </body>
    # </html>
    # """

    # chunks = pipeline.process(html)

    # for i, chunk in enumerate(chunks):
    #     print(f"--- Chunk {i + 1} ---")
    #     print(f"Content: {chunk.content[:100]}...")
    #     print(f"Headers: {[h['title'] for h in chunk.metadata.get('headers', [])]}")
    #     print(f"Size: {len(chunk.content)} chars")
    #     print()
