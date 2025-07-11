import asyncio
import json
from typing import cast, List
from patchright.async_api import Page, async_playwright
from actions.search import search
from actions.utils import get_best_selector
from actions.ai import load_sys_prompt, cerebras
from actions.utils import sanitize_filename


async def click_wrapper(webpage: Page, target: str, workflow_id =None):
    # get candidate button elements
    candidates = await get_button(webpage)
    print("Candidate buttons: ", candidates, "\n")
    # Prepare LLM input (strip element handles)
    llm_candidates = [
        {k: v for k, v in c.items() if k != "element"} for c in candidates
    ]
    # load sys prompt
    sys_prompt = await load_sys_prompt("micro")
    prompt = (
        f"Prompt action: {target}\n"
        f"Here is a list of clickable elements (with their HTML and attributes):\n"
        f"{json.dumps(llm_candidates, indent=2)}\n"
        'Return the index of the best match as a JSON object: {"action": <index>}'
    )
    # get result
    llm_res = await cerebras(prompt, sys_prompt)
    llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]

    print("LLM Output for text input analysis: ", llm_res, "\n")
    llm_json = json.loads(llm_res)
    # get result index 
    idx = int(llm_json["action"])
    # click using index 
    await click(idx, webpage, webpage.url, candidates, workflow_id=workflow_id)


async def extract_candidates(elements, max_candidates=30):
    candidates = []
    for el in elements:
        try:
            # Only consider visible elements
            visible = await el.is_visible()
            if not visible:
                continue
            outer_html = await el.evaluate("el => el.outerHTML")
            inner_html = await el.evaluate("el => el.innerHTML")
            aria_label = await el.get_attribute("aria-label")
            title = await el.get_attribute("title")
            alt = await el.get_attribute("alt")
            el_class = await el.get_attribute("class")
            el_id = await el.get_attribute("id")
            tag = await el.evaluate("el => el.tagName")
            candidates.append(
                {
                    "tag": tag,
                    "outer_html": outer_html[:300],  # limit length
                    "inner_html": inner_html[:100],  # limit length
                    "aria_label": aria_label,
                    "title": title,
                    "alt": alt,
                    "class": el_class,
                    "id": el_id,
                    "element": el,
                }
            )
        except Exception:
            continue
    # Prioritize candidates with aria-label/title/alt, then trim to max_candidates
    candidates.sort(
        key=lambda c: bool(c["aria_label"] or c["title"] or c["alt"]), reverse=True
    )
    return candidates[:max_candidates]


async def get_button(page: Page):
    # Aggregate all clickable elements
    all_elements = (
        await page.get_by_role("link").all()
        + await page.get_by_role("button").all()
        + await page.locator(
            "div[data-click], div[class*='click'], div[class*='button'], div[class*='link'], div[class*='nav'], div[class*='menu'], div[class*='tab'], div[class*='card'], div[class*='item']"
        ).all()
        + await page.locator(
            "[style*='cursor: pointer'], [style*='cursor:pointer'], [class*='cursor-pointer'], [class*='pointer']"
        ).all()
        + await page.locator(
            "[onclick], [onmousedown], [onmouseup], [data-action], [data-click], [data-href], [data-url]"
        ).all()
        + await page.locator(
            "[class*='btn'], [class*='button'], [class*='cta'], [class*='action'], [class*='submit'], [class*='primary'], [class*='secondary']"
        ).all()
        + await page.locator("[href]").all()
    )
    # Remove duplicates by outerHTML
    unique_by_html = {}
    for el in all_elements:
        try:
            outer_html = await el.evaluate("el => el.outerHTML")
            if outer_html not in unique_by_html:
                unique_by_html[outer_html] = el
        except Exception:
            continue
    unique_elements = list(unique_by_html.values())
    print("Unique elements: ", unique_elements)
    candidates = await extract_candidates(unique_elements)
    return candidates


async def click(candidate_idx, page: Page, site: str, candidates, workflow_id=None):
    # candidate_idx: integer index of the element to click
    if not (0 <= candidate_idx < len(candidates)):
        print("Invalid candidate index")
        return
    el = candidates[candidate_idx]["element"]
    current_url = page.url
    try:
        await el.click()
        async with page.expect_navigation(timeout=5000) as navigation_info:
            await navigation_info.value
            print(f"Navigation detected: {current_url} -> {page.url}")
        # After successful click, add to workflow if workflow_id is provided
        if workflow_id is not None:
            selector = await get_best_selector(el)
            from db.workflows import Workflows

            workflow = Workflows()
            workflow.add_step(
                id=workflow_id, step={"action": "click", "selector": selector}
            )
    except Exception:
        pass
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(10000)
    filename = sanitize_filename(site) + ".png"
    await page.screenshot(path=f"tools/actions/ss/{filename}")


async def test_get_button():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = await search("https://auth.openai.com/log-in", browser)

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
        await page.wait_for_load_state("domcontentloaded")
        res = await get_button(page)
        print("Candidates: ", res)


if __name__ == "__main__":
    asyncio.run(test_get_button())
