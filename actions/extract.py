import asyncio
from typing import List, cast
import chardet
from actions.ai import cerebras, load_sys_prompt, gpt
from bs4 import BeautifulSoup
from patchright.async_api import Page, async_playwright
from actions.search import search
from prompts.tools.gpt.gpt_summarizer import gpt_summarizer


async def extract(page: Page):
    html_content = await page.content()
    soup = BeautifulSoup(html_content, "html.parser")

    main_content = None
    main_selectors = [
        "article",
        "main",
        '[role="main"]',
        ".main-content",
        ".content",
        ".article-content",
        ".post-content",
        "#content",
        "#main",
        ".entry-content",
        ".page-content",
    ]

    for selector in main_selectors:
        main_content = soup.select_one(selector)
        if main_content and len(main_content.get_text(strip=True)) > 200:
            break

    # If no main content found, use body but be more selective
    if not main_content:
        main_content = soup.find("body") or soup

    # Now clean only within the main content area
    for tag in [
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "iframe",
        "noscript",
        "form",
    ]:
        # Remove all occurrences of the tag within main_content, if any
        for el in main_content.find_all(tag):
            el.decompose()
    # with open("output.txt", "w", encoding="utf-8") as f:
    #     f.write(main_content.get_text(separator="\n", strip=True))
    return main_content.get_text(separator="\n", strip=True)


async def extract_wrapper(page: Page):
    res = await extract(page)
    system_prompt = await load_sys_prompt("summarizer")
    user_prompt = "Create a descriptive summary of given text. Text: " + res
    # # llm_res = await cerebras(
    # #     user_prompt=user_prompt,
    # #     system_prompt=system_prompt,
    # # )

    prompt = gpt_summarizer(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        model="gpt-4.1-nano-2025-04-14",
    )

    llm_res = await gpt(prompt)

    # llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
    return llm_res
    # return res


async def test_search_and_extract():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        webpage = await search(
            "https://en.wikipedia.org/wiki/Donald_Trump", browser=browser
        )
        # await extract(webpage)
        llm_res = await extract_wrapper(page=webpage)

        print("LLM Output for summary: ", llm_res, "\n")


if __name__ == "__main__":
    asyncio.run(test_search_and_extract())
