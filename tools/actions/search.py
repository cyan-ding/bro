from patchright.async_api import BrowserContext

# tool to search things on the internet


async def search(request: str, browser: BrowserContext):
    page = await browser.new_page()
    await page.goto(request)
    await page.wait_for_load_state("networkidle")
    return page
