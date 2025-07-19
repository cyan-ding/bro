import asyncio
import json
import os
import base64
from typing import cast, List, Dict, Any, Optional
from httpx import TimeoutException
from patchright.async_api import Page, Locator
from actions.utils import SelectorOptions, check_if_action_worked, fuzzy_action_fallback
from actions.ai import load_sys_prompt, gpt
from actions.text_input import draw_bounding_boxes
from prompts.tools.gpt.gpt_summarizer import gpt_summarizer


async def click_wrapper(
    webpage: Page, target: str, workflow_id: Optional[Any] = None
) -> bool:
    """
    Wrapper function that:
    1) gets all button candidates on the webpage
    2) queries LLM (OpenAI multimodal) to select one candidate
    3) attempts to click on that candidate
    Args:
        webpage: The Playwright Page object
        target: The semantic target to click (e.g. 'submit', 'next', etc)
        workflow_id: Optional workflow identifier
    Returns:
        True if click was successful, False otherwise
    """
    # get candidate button elements
    candidates = await get_buttons(webpage)
    print("Candidate buttons: ", candidates, "\n")
    # Prepare LLM input (strip element handles, add index)
    llm_candidates = [
        {**{k: v for k, v in c.items() if k != "element"}, "index": i} for i, c in enumerate(candidates)
    ]
    print("LLM candidates: ", llm_candidates)

    # Draw bounding boxes with indices
    bounding_boxes = []
    for c in candidates:
        bbox = await c["element"].bounding_box()
        if bbox:
            bounding_boxes.append(bbox)
    js_path = os.path.join(os.path.dirname(__file__), "assets", "draw_bounding_boxes.js")
    await draw_bounding_boxes(webpage, bounding_boxes, js_path)

    # Take screenshot with bounding boxes visible
    screenshot_path = "temp_screenshot_with_boxes.png"
    await webpage.screenshot(path=screenshot_path, full_page=True)
    # Remove the overlay after taking screenshot
    # await webpage.evaluate("() => { const overlay = document.getElementById('bro-bbox-overlay'); if (overlay) overlay.remove(); }")

    # Read screenshot as base64 for GPT
    with open(screenshot_path, "rb") as image_file:
        screenshot_base64 = base64.b64encode(image_file.read()).decode('utf-8')

    # load sys prompt
    sys_prompt = await load_sys_prompt("micro")
    prompt = (
        f"Prompt action: {target}\n"
        f"Here is a list of clickable elements (with their HTML and attributes). Each element is assigned an 'index' field, which matches the red number in the screenshot.\n"
        f"{json.dumps(llm_candidates, indent=2)}\n"
        "I've also provided a screenshot of the page with red bounding boxes drawn around detected clickable elements, each labeled with its index.\n"
        'Return the index (the integer) of the best match as a JSON object: {"action": <index>, "p": <probability>}'
        "Return index -1 if no good match could be found. Do not return the full element, only the index."
    )
    # Prepare OpenAI Responses API input
    gpt_params = gpt_summarizer(
        user_prompt=prompt,
        system_prompt=sys_prompt,
        model="gpt-4.1-nano-2025-04-14"
    )
    gpt_params["input"][0]["content"] = [
        {
            "type": "input_text",
            "text": prompt
        },
        {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{screenshot_base64}"
        }
    ]
    llm_res = await gpt(gpt_params)
    # Clean up temporary screenshot
    if os.path.exists(screenshot_path):
        os.remove(screenshot_path)
    print("LLM Output for click analysis: ", llm_res, "\n")
    # Extract the content from GPT Responses API
    if llm_res is not None and hasattr(llm_res, 'output') and llm_res.output:
        llm_content = llm_res.output[0].content[0].text
    else:
        print("Failed to get valid response from GPT")
        return False
    try:
        llm_json = json.loads(llm_content)
    except json.JSONDecodeError:
        print("Failed to parse LLM response as JSON, trying to extract JSON from text")
        import re
        json_match = re.search(r'\{.*\}', llm_content)
        if json_match:
            llm_json = json.loads(json_match.group())
        else:
            print("Could not extract JSON from LLM response")
            return False
    # click using index
    try:
        idx = int(llm_json["action"])
        if idx == -1:
            # try fuzzy fallback
            idx = fuzzy_action_fallback(target=target, candidates=llm_candidates)
            if idx == -1:
                print("No good match found, failed to click on", target)
                return False
        details = await check_if_action_worked(
            webpage,
            lambda: click(
                idx, webpage, webpage.url, candidates, workflow_id=workflow_id
            ),
        )
        await webpage.wait_for_timeout(5000)
        if details:
            print(f"Successfully clicked on target {target}, induced a {details}")
            return True
        else:
            print(f"Failed to induce DOM change with click on target {target}")
            return False
    except TimeoutException as e:
        print(f"Failed to click on target {target}, exception: {e}")
        return False


async def extract_element_data(element: Locator) -> Optional[Dict[str, Any]]:
    """
    Extracts relevant data from a single Locator in one browser evaluation.
    Args:
        element: Playwright Locator
    Returns:
        Dictionary of element attributes, or None if not visible
    """
    return await element.evaluate("""el => {
        if (!el.offsetParent) return null; // A simple visibility check
        return {
            tag: el.tagName.toLowerCase(),
            outer_html: el.outerHTML.slice(0, 300),
            inner_text: el.innerText.slice(0, 200), // innerText is often more useful
            aria_label: el.getAttribute('aria-label'),
            title: el.getAttribute('title'),
            alt: el.getAttribute('alt'),
            el_class: el.className,
            el_id: el.id,
            href: el.getAttribute('href'),
        };
    }""")


async def get_buttons(page: Page, max_candidates: int = 30) -> List[Dict[str, Any]]:
    """
    Finds, filters, and extracts data from interactive elements on a page.
    Args:
        page: Playwright Page object
        max_candidates: Maximum number of candidates to return
    Returns:
        List of candidate element dictionaries
    """
    await page.wait_for_load_state("networkidle")
    selectors = [
        "a",
        "button",
        "input[type='button']",
        "input[type='submit']",
        "input[type='reset']",
        "input[type='radio']",
        "input[type='checkbox']",
        "label[for]",
        "summary",
        "select",
        "option",
        "area[href]",
        "[role='button']",
        "[role='link']",
        "[role='checkbox']",
        "[role='radio']",
        "[role='tab']",
        "[role='switch']",
        "[role='option']",
        "[role='menuitem']",
        "[role='menuitemcheckbox']",
        "[role='menuitemradio']",
        "[role='treeitem']",
        "[role='combobox']",
        "[role='listbox']",
        "[role='slider']",
        "[role='spinbutton']",
        "[onclick]",
        "[onmousedown]",
        "[data-action]",
        "[data-click]",
        "[style*='cursor: pointer']",
        "[tabindex]:not([tabindex='-1'])",
        "svg[onclick]",
        "[role='img'][onclick]",
    ]
    # Locate all potential elements in one go
    all_elements_locator = page.locator(", ".join(selectors))
    all_elements = await all_elements_locator.all()
    # --- Efficient Data Extraction and Filtering ---
    # Use asyncio.gather to perform evaluations in parallel
    tasks = [extract_element_data(el) for el in all_elements]
    results = await asyncio.gather(*tasks)
    # Filter out invisible or irrelevant elements and add the handle back
    visible_candidates = []
    seen_html = set()
    for i, data in enumerate(results):
        if data and data["outer_html"] not in seen_html:
            seen_html.add(data["outer_html"])
            data["element"] = all_elements[i]  # Re-attach the element handle
            visible_candidates.append(data)
    # --- Prioritization and Selection ---
    # Prioritize elements with more specific and meaningful attributes
    def sort_key(c: Dict[str, Any]) -> tuple:
        return (
            bool(c["aria_label"]),  # Most important
            bool(c["title"]),  # Then title
            bool(c["href"] and not c["href"] == "#"),  # Then meaningful href
            bool(c["inner_text"].strip()),  # Finally, non-empty text
        )
    visible_candidates.sort(key=sort_key, reverse=True)
    print(f"Found {len(visible_candidates)} unique and visible interactive elements.")
    return visible_candidates[:max_candidates]


async def click(
    candidate_idx: int,
    page: Page,
    site: str,
    candidates: List[Dict[str, Any]],
    workflow_id: Optional[Any] = None
) -> None:
    """
    Clicks the candidate at the given index.
    Args:
        candidate_idx: Index of the element to click
        page: Playwright Page object
        site: URL of the site
        candidates: List of candidate element dicts
        workflow_id: Optional workflow identifier
    """
    if not (0 <= candidate_idx < len(candidates)):
        print("Invalid candidate index")
        return
    el = candidates[candidate_idx]["element"]
    try:
        await el.click()
        # After successful click, add to workflow if workflow_id is provided
        if workflow_id is not None:
            options = SelectorOptions()
            selectors = await options.create_options(locator=el)
            from db.workflows import Workflows
            workflow = Workflows()
            workflow.add_step(
                id=workflow_id, step={"action": "click", "selector": selectors}
            )
    except Exception:
        pass
    await page.wait_for_load_state("networkidle")


async def main():
    """
    Test function for click_wrapper.
    Sets up a browser page and tests click functionality on a sample website.
    """
    from patchright.async_api import async_playwright
    import asyncio

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)  # Set to True for headless mode
        page = await browser.new_page()
        try:
            # Navigate to a test page with clickable elements
            print("Navigating to test page...")
            await page.goto("https://httpbin.org/forms/post")
            await page.wait_for_load_state("networkidle")
            # Test click wrapper
            print("Testing click_wrapper...")
            success = await click_wrapper(
                webpage=page,
                target="submit",
                workflow_id="test_workflow_456"
            )
            if success:
                print("✅ Click test successful!")
            else:
                print("❌ Click test failed!")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Error during test: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
