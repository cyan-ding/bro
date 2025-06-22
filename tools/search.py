from patchright.async_api import BrowserContext, Page

# tool to search things on the internet


async def search(request: str, browser: BrowserContext):
    page = await browser.new_page()

    processed_req = "+".join(request.split(" "))
    await page.goto(f"https://google.com/search?q={processed_req}")
    await page.wait_for_load_state("networkidle")
    await page.screenshot(path="./temp/screenshots.png")
    content = await extract_first_result(page)
    await page.close()
    return content


async def extract_first_result(page: Page):
    """
    Finds the first Google search result, clicks on it, waits for the new page to load,
    and then extracts the text content from the body of the new page.
    """
    # This selector targets the main link within the first search result block.
    # It might need to be adjusted if Google's page structure changes.
    first_link_selector = "div.g a h3"

    first_link = page.locator(first_link_selector).first

    if await first_link.count() == 0:
        # If the primary selector fails, try a more general one.
        first_link_selector = "a[href^='http'] h3"
        first_link = page.locator(first_link_selector).first
        if await first_link.count() == 0:
            return "No search results found."

    try:
        # Click the link and wait for the navigation to complete.
        await first_link.click()
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception as e:
        return f"An error occurred while clicking the link or loading the page: {e}"

    # Extract the text content from the body of the new page.
    page_content = await page.evaluate("() => document.body.innerText")

    return page_content


