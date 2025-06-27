from patchright.async_api import BrowserContext

# tool to search things on the internet


async def search(request: str, browser: BrowserContext):
    page = await browser.new_page()

    # processed_req = "+".join(request.split(" "))
    await page.goto(request)
    # await page.goto(f"https://google.com/search?q={processed_req}")
    await page.wait_for_load_state("networkidle")
    # await page.screenshot(path="./temp/screenshots.png")
    # content = await extract_first_result(page)
    # await page.close()
    return page
