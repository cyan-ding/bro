"""
Actions are the functions given to the LLM that are used to interact with the page.
All actions now use XPath selectors for precise element targeting, with optional iframe context.
"""

from typing import Any, Optional

from patchright.async_api import Page
from .agent_state import AgentState
import re
from typing import Sequence
from bs4 import BeautifulSoup
from bs4.element import Comment
from markdownify import markdownify as md


def _resolve_locator(
    page: Page, target: str, iframe_xpath: Optional[str] = None
) -> Any:
    """Return a Locator targeting the element XPath within an optional iframe.

    Args:
        page: Playwright page object.
        target: XPath selector for the target element.
        iframe_xpath: Optional XPath selector for the containing iframe.

    Returns:
        A Playwright Locator scoped appropriately.
    """
    if iframe_xpath:
        frame = page.frame_locator(f"xpath={iframe_xpath}")
        return frame.locator(f"xpath={target}")
    return page.locator(f"xpath={target}")


async def input_text(
    page: Page,
    target: str,
    input_text: str,
    iframe_xpath: Optional[str] = None,
    agent_state=None,
) -> None:
    """Enter text into an input field using multiple strategies.

    Args:
        page: The browser page.
        target: XPath selector for the input element.
        input_text: Text to enter into the field.
        iframe_xpath: Optional XPath selector for the parent iframe containing the element.
    """
    # Find the element using XPath, optionally within an iframe
    element = _resolve_locator(page, target, iframe_xpath)

    if not await element.count():
        raise ValueError(f"No element found with XPath: {target}")

    # Define input strategies
    async def strategy_fill() -> bool:
        """Try fill() method"""
        try:
            await element.fill(input_text, timeout=5000)
            return True
        except Exception as e:
            print(f"Fill strategy failed: {e}")
            return False

    async def strategy_type() -> bool:
        """Try type() method with delay"""
        try:
            await element.type(input_text)
            return True
        except Exception as e:
            print(f"Type strategy failed: {e}")
            return False

    async def strategy_keyboard() -> bool:
        """Try keyboard typing"""
        try:
            await page.keyboard.type(input_text)
            return True
        except Exception as e:
            print(f"Keyboard strategy failed: {e}")
            return False

    async def strategy_force_fill() -> bool:
        """Try fill with force=True"""
        try:
            await element.fill(input_text, force=True)
            return True
        except Exception as e:
            print(f"Force fill strategy failed: {e}")
            return False

    # Try strategies in order
    strategies = [strategy_fill, strategy_type, strategy_keyboard, strategy_force_fill]

    for strategy in strategies:
        if await strategy():
            print(f"Successfully entered text using {strategy.__name__}")


            return

    raise Exception("All text input strategies failed")


async def click(page: Page, target: str, iframe_xpath: Optional[str] = None) -> None:
    """Click on an element using an XPath selector, optionally within an iframe.

    Args:
        page: The browser page.
        target: XPath selector for the element to click.
        iframe_xpath: Optional XPath selector for the parent iframe containing the element.
    """
    element = _resolve_locator(page, target, iframe_xpath)

    if not await element.count():
        raise ValueError(f"No element found with XPath: {target}")

    try:
        await element.click(timeout=5000)
    except Exception:
        print("Failed to click element: Timed out")


async def scroll(page: Page, how_much: int):
    """
    Scroll the page by the specified amount.

    Args:
            page: The browser page
            how_much: Number of pixels to scroll (positive for down, negative for up)
    """
    await page.evaluate(f"window.scrollBy(0, {how_much})")


def _remove_comments_and_noncontent(root: BeautifulSoup) -> None:
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


def _remove_unwanted_sections(text: str) -> str:
    """Remove unwanted sections like references, citations, sources, etc."""
    # Remove Wikipedia-style citation links like [[184]](#cite_note-187)
    text = re.sub(r"\[\[\d+\]\]\(#cite_note[^)]*\)", "", text)

    # Remove Wikipedia edit links like [edit](/w/index.php?title=...&action=edit&section=25 "Edit section: ...")
    text = re.sub(r"\[edit\]\([^)]*\)", "", text)

    # Remove additional edit section links like [&action=edit&section=1 "Edit section: History")]
    text = re.sub(r"\[&action=edit&section=[^\]]*\]", "", text)

    # Remove markdown images like ![Wikipedia](/static/images/mobile/copyright/wikipedia-wordmark-en.svg)
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


def _html_to_markdown(html: str) -> str:
    """Convert HTML to markdown using markdownify, removing unwanted sections."""
    # fallback using beautifulsoup to strip script tags
    soup = BeautifulSoup(html, "html.parser")
    _remove_comments_and_noncontent(soup)
    html = str(soup)

    normalized_html = md(
        html,
        heading_style="ATX",  # Use # headers
        bullets="-",  # Use - for bullets
        escape_misc=False,  # Don't escape special chars
    )

    return _remove_unwanted_sections(normalized_html)




async def extract(
    page: Page,
    agent_state: Optional[AgentState] = None,
) -> str:
    """
    Extract content from the current page and convert to markdown.

    Args:
        page: The browser page
        agent_state: Agent state manager for tracking extraction descriptions

    Returns:
        Content extraction result with markdown content
    """
    try:
        # Get the page HTML content
        html_content = await page.content()
        page_url = page.url
        page_title = await page.title()

        print(f"🔄 Extracting content from: {page_url}")

        # Extract content using HTML to markdown conversion
        try:
            extracted_content = _html_to_markdown(html_content)
        except Exception as e:
            extracted_content = f"Error extracting content, defaulting to whole page content: {str(e)}"
            extracted_content = await page.evaluate("""
                () => {
                    const body = document.body;
                    return body ? body.innerText : '';
                }
            """)

            if not extracted_content.strip():
                extracted_content = "No content could be extracted from this page."

        print(f"✅ Content extracted ({len(extracted_content)} characters)")

        # Add content to agent_state for tracking
        if agent_state:
            agent_state.add_extraction(
                content=extracted_content,
                source_url=page_url[:30],
                source_title=page_title or "Unknown Page"
            )

        # Return the extracted content directly
        result = f"""Content Extraction Complete:
            - Source: {page_title} ({page_url})
            - Content length: {len(extracted_content)} characters

            Extracted Content:
            {extracted_content}"""

        return result

    except Exception as e:
        error_msg = f"Error during content extraction: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg

async def search(
    page: Page,
    query: str,
    tab_index: Optional[int] = None,
    agent_state: Optional[AgentState] = None,
    new_tab: bool = False,
):
    """
    Search Google for the query and navigate to results, or switch to an existing tab.

    Args:
        page: The browser page
        query: The search query (ignored if tab_index is provided)
        tab_index: Optional zero-based index of an existing tab to switch to instead of searching
        agent_state: Agent state manager for getting tab information
        new_tab: If True, open the search in a new tab instead of navigating the current tab
    """
    import urllib.parse

    # Handle switching to a new tab for search
    context = page.context

    if tab_index is not None:
        target_tab = agent_state.get_tab_by_index(tab_index)
        if not target_tab:
            print(f"⚠️ No tab found at index {tab_index}, cannot switch to non-existent tab")
            return
        target_page = next((p for p in context.pages if p.url == target_tab.url), None)
        if target_page:
            await target_page.bring_to_front()
            await agent_state.set_current_tab_index(tab_index)
            return
        else:
            print(f"⚠️ Tab {tab_index} not found in browser context, cannot switch to tab")
            return
    if new_tab:
        try:
            new_page = await context.new_page()
            page_to_use = new_page
        except Exception as e:
            print(f"⚠️ Error creating new tab for search: {e}")
            page_to_use = page  # Fallback to current tab
    else:
        page_to_use = page

    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.google.com/search?q={encoded_query}"
    await page_to_use.goto(search_url, wait_until="load")

    if new_tab:
        try:
            agent_state.add_tab_state(page_to_use.url, await page_to_use.title(), is_active=True)
            await page_to_use.bring_to_front()
            await agent_state.set_current_tab_index(len(agent_state.tabs) - 1)
        except Exception as e:
            print(f"⚠️ Failed to update agent state for new tab: {e}")






async def todo_edit(todo_items: list, agent_state: Optional[AgentState] = None) -> str:
    """
    Update the agent's todo list with a structured list of todo items.

    Args:
        todo_items: List of TodoItem objects or dictionaries with 'task' and 'completed' keys
        agent_state: Agent state manager for tracking todo list

    Returns:
        Success message confirming the todo list update
    """
    if not agent_state:
        return "Error: Agent state not available"

    try:
        # Convert TodoItem objects to dictionaries if needed
        if todo_items and hasattr(todo_items[0], 'model_dump'):
            todo_items_dict = [item.model_dump() for item in todo_items]
        else:
            todo_items_dict = todo_items

        result = agent_state.update_todo_list(todo_items_dict)
        print(f"📝 {result}")
        return result
    except Exception as e:
        error_msg = f"Error updating todo list: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg


async def done(reason: str):
    """
    Signal that the user's task is completed or that the agent is unable to proceed.
    Instead of stopping, this now notifies the user and awaits their decision.

    Args:
            reason: The reason for completion or stopping
    """
    # This function serves as a signal to notify the user for decision
    # The actual user interaction logic is handled in the agent loop
    print(f"🤖 Agent believes task is complete: {reason}")
    return f"AWAIT_USER_DECISION: {reason}"
