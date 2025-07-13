import asyncio

from patchright.async_api import async_playwright, Page, BrowserContext
from actions.search import search
from bro.roles.worker import click_wrapper, text_input_wrapper


async def login(page: Page, browser: BrowserContext, workflow_id=None):
    """
    Automates logging into a site using 'Log in with Google'.
    Fills email and password fields if needed, and clicks the 'Log in with Google' button.
    """
    email = input("Input email: ")
    password = input("Input password: ")
    # 1. Find and click the 'Log in with Google' button
    await click_wrapper(page, "Login with Google", workflow_id=workflow_id)

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
        google_page=page

    # 3. Fill in the email/email field

    await text_input_wrapper(
        webpage=google_page,
        target="Email text field",
        input_text=email,
        workflow_id=workflow_id,
    )

    # 4. Click 'Next' after email
    await click_wrapper(google_page, "Next button", workflow_id=workflow_id)


    # 5. Fill in the password field
    await text_input_wrapper(
        webpage=google_page,
        target="Password text field",
        input_text=password,
        workflow_id=workflow_id,
    )
    # 6. Click 'Next' after password
    await click_wrapper(google_page, "Next button", workflow_id=workflow_id)
    await google_page.wait_for_timeout(3000)
    print("Succesfully logged in with Google")


async def test_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        workflow_id = "test_login"
        page = await search("https://github.com/", browser, workflow_id=workflow_id)
        await click_wrapper(page, "Log in", workflow_id=workflow_id)
        await page.wait_for_timeout(3000)
        await login(page, browser, workflow_id=workflow_id)


if __name__ == "__main__":
    asyncio.run(test_login())
