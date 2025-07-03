import asyncio

from patchright.async_api import async_playwright, Page, BrowserContext

from actions.click import click, get_button
from actions.search import search
from actions.text_input import enter_input, get_text_input
from bro.roles.worker import click_wrapper


async def login(page: Page, browser: BrowserContext):
    """
    Automates logging into a site using 'Log in with Google'.
    Fills email and password fields if needed, and clicks the 'Log in with Google' button.
    """
    email = input("Input email: ")
    password = input("Input password: ")

    # 1. Find and click the 'Log in with Google' button
    candidates = await get_button(page)
    google_btn_idx = None
    for idx, c in enumerate(candidates):
        # Look for Google login button by text or aria-label
        if (
            (c.get("aria_label") and "google" in c["aria_label"].lower())
            or (c.get("title") and "google" in c["title"].lower())
            or (c.get("inner_html") and "google" in c["inner_html"].lower())
        ):
            google_btn_idx = idx
            break
    if google_btn_idx is None:
        print("Could not find 'Log in with Google' button.")
    else:
        await click(google_btn_idx, page, page.url, candidates)

    # 2. Switch to the Google login popup/page
    # Wait for new page (popup)
    google_page = None
    for _ in range(10):
        await asyncio.sleep(1)
        new_pages = [
            pg
            for pg in browser.pages
            if pg.url.startswith("https://accounts.google.com")
        ]
        if new_pages:
            google_page = new_pages[0]
            break
    if not google_page:
        print("Google login popup did not appear.")
        return

    # 3. Fill in the email/email field
    input_candidates = await get_text_input(google_page)
    email_input = None
    for c in input_candidates:
        text_blob = (
            (c.get("placeholder") or "")
            + (c.get("aria_label") or "")
            + (c.get("label") or "")
            + (c.get("outer_html") or "")
            + (c.get("inner_html") or "")
        ).lower()
        if "email" in text_blob or "identifier" in text_blob:
            email_input = c
            break
    if not email_input:
        # fallback: just use the first input
        email_input = input_candidates[0] if input_candidates else None
    if not email_input:
        print("Could not find email input field.")
        return
    await enter_input(email_input, google_page, "google_login", email)

    # 4. Click 'Next' after email
    btn_candidates = await get_button(google_page)
    next_btn_idx = None
    for idx, c in enumerate(btn_candidates):
        text_blob = (
            (c.get("inner_html") or "")
            + (c.get("aria_label") or "")
            + (c.get("outer_html") or "")
        ).lower()
        print(f"Candidate {idx}: {text_blob}")

        if "next" in text_blob:
            next_btn_idx = idx
            break
    if next_btn_idx is not None:
        await click(next_btn_idx, google_page, "google_login", btn_candidates)
    else:
        print("Could not find Next button")
    await asyncio.sleep(2)

    # 5. Fill in the password field
    input_candidates = await get_text_input(google_page)
    password_input = None
    for c in input_candidates:
        text_blob = (
            (c.get("placeholder") or "")
            + (c.get("aria_label") or "")
            + (c.get("label") or "")
            + (c.get("outer_html") or "")
            + (c.get("inner_html") or "")
        ).lower()
        if "password" in text_blob:
            password_input = c
            break
    if not password_input:
        # fallback: just use the first input
        password_input = input_candidates[0] if input_candidates else None
    if not password_input:
        print("Could not find password input field.")
        return
    await enter_input(password_input, google_page, "google_login", password)

    # 6. Click 'Next' after password
    btn_candidates = await get_button(google_page)
    next_btn_idx = None
    for idx, c in enumerate(btn_candidates):
        if (c.get("inner_html") and "next" in c["inner_html"].lower()) or (
            c.get("aria_label") and "next" in c["aria_label"].lower()
        ):
            next_btn_idx = idx
            break
    if next_btn_idx is not None:
        await click(next_btn_idx, google_page, "google_login", btn_candidates)
    print("Login flow attempted. Check browser for result.")


async def test_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = await search("https://chatgpt.com", browser)
        await click_wrapper(page, "Log in")
        await page.wait_for_timeout(3000)
        await login(page, browser)

if __name__ == "__main__":
    asyncio.run(test_login())
