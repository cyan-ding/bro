"""
Actions are the functions given to the LLM that are used to interact with the page.
All actions now use XPath selectors for precise element targeting.
"""

import trafilatura
from patchright.async_api import Page


async def input_text(page: Page, target: str, input_text: str):
    """
    Enter text into an input field using multiple strategies.

    Args:
            page: The browser page
            target: XPath selector for the input element
            input_text: Text to enter into the field
    """
    # Find the element using XPath
    element = page.locator(f"xpath={target}")

    if not await element.count():
        raise ValueError(f"No element found with XPath: {target}")

    # always click on the text field first
    await element.click(timeout=5000)

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
            await element.type(input_text, delay=200)
            return True
        except Exception as e:
            print(f"Type strategy failed: {e}")
            return False

    async def strategy_keyboard() -> bool:
        """Try keyboard typing"""
        try:
            await element.focus(timeout=5000)
            await page.keyboard.type(input_text, delay=50)
            return True
        except Exception as e:
            print(f"Keyboard strategy failed: {e}")
            return False

    async def strategy_force_fill() -> bool:
        """Try fill with force=True"""
        try:
            await element.fill(input_text, force=True, timeout=5000)
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


async def click(page: Page, target: str):
    """
    Click on an element using XPath selector.

    Args:
            page: The browser page
            target: XPath selector for the element to click
    """
    element = page.locator(f"xpath={target}")

    if not await element.count():
        raise ValueError(f"No element found with XPath: {target}")

    await element.click(timeout=5000)


async def scroll(page: Page, how_much: int):
    """
    Scroll the page by the specified amount.

    Args:
            page: The browser page
            how_much: Number of pixels to scroll (positive for down, negative for up)
    """
    await page.evaluate(f"window.scrollBy(0, {how_much})")


async def extract(page: Page):
    """
    Extract main text content from the page using Trafilatura.

    Args:
            page: The browser page

    Returns:
            Extracted text content
    """
    # Get the page HTML
    html_content = await page.content()

    # Extract text using Trafilatura
    extracted_text = trafilatura.extract(
        html_content, include_links=True, include_images=True
    )

    if not extracted_text:
        # Fallback to basic text extraction
        extracted_text = await page.evaluate("""
			() => {
				const body = document.body;
				return body ? body.innerText : '';
			}
		""")

    return extracted_text


async def search(page: Page, query: str):
    """
    Search Google for the query and navigate to results.

    Args:
            page: The browser page
            query: The search query
    """
    # URL encode the query
    import urllib.parse

    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.google.com/search?q={encoded_query}"

    await page.goto(search_url, wait_until="load")


async def write_file(content: str, session_id: str = None):
    """
    Write content to the session's todo.md file.

    Args:
            content: The content to write to the todo.md file
            session_id: Optional session ID for session-specific files
    """
    from pathlib import Path

    # Use session-specific filename if session_id is provided
    if session_id:
        file_path = Path(f"todo_{session_id}.md")
    else:
        file_path = Path("todo.md")

    # Write the content to the file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


async def done(reason: str):
    """
    Signal that the user's task is completed or that the agent is unable to proceed.

    Args:
            reason: The reason for completion or stopping
    """
    # This function serves as a signal to stop the agent execution
    # The actual stopping logic is handled in the agent loop
    print(f"Task completion signaled: {reason}")
    return f"Task completed: {reason}"
