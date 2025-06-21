from playwright.async_api import async_playwright, Browser

# tool to search things on the internet

async def search(request: str, browser: Browser):
    page = await browser.new_page()
    processed_req = "+".join(request.split(" "))
    await page.goto(f"https://google.com/search?q={processed_req}")
    await page.wait_for_load_state("networkidle")
    await page.screenshot(path="screenshots.png")
    results = extract_search(page)
    return results


def extract_search(page):
    results = page.query_selector_all("div.g")
    return results
        