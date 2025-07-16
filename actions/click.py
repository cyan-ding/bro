import asyncio
import json
from typing import cast, List, Dict, Any
from httpx import TimeoutException
from patchright.async_api import Page, Locator
from actions.utils import SelectorOptions, check_if_action_worked, fuzzy_action_fallback
from actions.ai import load_sys_prompt, cerebras


async def click_wrapper(webpage: Page, target: str, workflow_id=None) -> bool:
    """
    Wrapper function that
    1) gets all button candidates on the webpage
    2) queries LLM to select one candidate
    3) attempts to click on that candidate
    """
    # get candidate button elements
    candidates = await get_buttons(webpage)
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
        'Return the index of the best match as a JSON object: {"action": <index>, "p": <probability>}'
        "Return index -1 if no good match could be found"
    )

    micro_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "integer"},
            "p": {"type": "number"},
        },
        "required": ["action", "p"],
        "additionalProperties": False,
    }
    # get result
    llm_res = await cerebras(
        prompt, sys_prompt, schema=micro_schema, model="qwen-3-235b-a22b"
    )
    llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]

    print("LLM Output for text input analysis: ", llm_res, "\n")
    llm_json = json.loads(llm_res)

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


async def extract_element_data(element: Locator) -> Dict[str, Any]:
    """
    Extracts relevant data from a single Locator in one browser evaluation.
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


async def click(candidate_idx, page: Page, site: str, candidates, workflow_id=None):
    # candidate_idx: integer index of the element to click
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
