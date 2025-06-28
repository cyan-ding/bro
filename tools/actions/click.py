import re
from difflib import get_close_matches

from patchright.async_api import Page

candidates = []


def sanitize_filename(name):
    """Sanitize filename to be safe for filesystem"""
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)


async def extract_texts(elements):
    texts = []
    for el in elements:
        text = await el.inner_text()
        if text.strip():
            texts.append(text)
            candidates.append((text, el))
    return texts


async def get_button(page: Page):
    # Get explicit links and buttons
    links = await page.get_by_role("link").all()
    buttons = await page.get_by_role("button").all()

    # Get divs and other elements that might be clickable
    clickable_divs = await page.locator(
        "div[data-click], div[class*='click'], div[class*='button'], div[class*='link'], div[class*='nav'], div[class*='menu'], div[class*='tab'], div[class*='card'], div[class*='item']"
    ).all()

    # Get elements with cursor pointer (often indicates clickable)
    pointer_elements = await page.locator(
        "[style*='cursor: pointer'], [style*='cursor:pointer'], [class*='cursor-pointer'], [class*='pointer']"
    ).all()

    # Get elements with click handlers
    click_handlers = await page.locator(
        "[onclick], [onmousedown], [onmouseup], [data-action], [data-click], [data-href], [data-url]"
    ).all()

    # Get elements with button-like classes
    button_like = await page.locator(
        "[class*='btn'], [class*='button'], [class*='cta'], [class*='action'], [class*='submit'], [class*='primary'], [class*='secondary']"
    ).all()

    # Get any element with href attribute (not just anchor tags)
    href_elements = await page.locator("[href]").all()

    link_texts = await extract_texts(links)
    button_texts = await extract_texts(buttons)
    div_texts = await extract_texts(clickable_divs)
    pointer_texts = await extract_texts(pointer_elements)
    handler_texts = await extract_texts(click_handlers)
    button_like_texts = await extract_texts(button_like)
    href_texts = await extract_texts(href_elements)

    # Remove duplicates and combine all clickable elements
    all_clickable = list(
        set(
            link_texts
            + button_texts
            + div_texts
            + pointer_texts
            + handler_texts
            + button_like_texts
            + href_texts
        )
    )

    return all_clickable
    # {
    #     "links": link_texts,
    #     "buttons": button_texts,
    #     "clickable_divs": div_texts,
    #     "pointer_elements": pointer_texts,
    #     "click_handlers": handler_texts,
    #     "button_like": button_like_texts,
    #     "href_elements": href_texts,
    #     "all_clickable": all_clickable,
    # }


# click the closest button that corresponds to llm_input
async def click(llm_input, page: Page, site: str):
    texts = [text for text, _ in candidates]
    retries = 10
    closest = get_close_matches(llm_input, texts, n=retries, cutoff=0.6)

    if closest:
        for retry in range(0, retries):
            matched_text = closest[retry]
            matched_locator = next(
                locator for text, locator in candidates if text == matched_text
            )

            # Store current URL to detect navigation
            current_url = page.url

            # Click with navigation handling
            try:
                await matched_locator.click()
                # Method 1: Wait for navigation if it occurs
                async with page.expect_navigation(timeout=5000) as navigation_info:
                    # Navigation occurred, wait for it to complete
                    await navigation_info.value
                    print(f"Navigation detected: {current_url} -> {page.url}")
                    break  # Success! Exit the retry loop
            except TimeoutError:
                continue  # try next candidate
    else:
        print("No matches, no clicks")
        return

    # Wait for the page to be fully loaded (whether navigated or not)
    await page.wait_for_load_state("networkidle")

    # Sanitize filename and take screenshot
    filename = sanitize_filename(site) + ".png"

    await page.screenshot(path=f"tools/actions/ss/{filename}")
