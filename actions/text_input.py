import asyncio
import json
from httpx import TimeoutException
from patchright.async_api import Locator, Page
from actions.utils import SelectorOptions, check_if_action_worked, fuzzy_action_fallback
from actions.ai import load_sys_prompt, cerebras
from typing import cast, List, Dict, Any, Callable, Coroutine



# Standard timeout for waiting for elements to become interactive.
INTERACTION_TIMEOUT_MS = 5000

async def text_input_wrapper(
    webpage: Page, target: str, input_text: str, workflow_id=None
) -> bool:
    """
    Wrapper function that
    1) gets all text input candidates on the webpage
    2) queries LLM to select one candidate
    3) attempts to fill in `input_text` into that candidate
    """
    # list text input candidates
    candidates = await get_text_inputs(webpage)
    # filter out locator (interpreter will throw TypeError, Locators aren't serializable)
    llm_candidates = [
        {k: v for k, v in c.items() if k != "element"} for c in candidates
    ]
    print("Candidate text inputs: ", llm_candidates)
    # ai inference
    sys_prompt = await load_sys_prompt("micro")
    
    prompt = (
        f"Prompt action: {target}\n"
        f"Here is a list of text input elements (with their HTML and attributes):\n"
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

    llm_res = await cerebras(prompt, sys_prompt, schema=micro_schema, model="llama-4-scout-17b-16e-instruct")

    # process output
    llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
    print("LLM Output for text input analysis: ", llm_res, "\n")
    llm_json = json.loads(llm_res)

    # attempt to enter text
    try:
        idx = int(llm_json["action"])
        if idx == -1:
            idx = fuzzy_action_fallback(target=target, candidates=llm_candidates)
            if idx == -1: 
                print("No good match found, failed to input text into ", target)
                return False
        changed, details = await check_if_action_worked(
            webpage, 
            lambda: enter_input(
                candidate_idx=idx,
                candidates=candidates,
                input_text=input_text,
                page=webpage,
                workflow_id=workflow_id,
            )
        ) 
        if changed:
            print(f"Successfully filled in text to target {target}, induced a {details}")
        else: 
            print(f"Failed to induce DOM change with input text into target {target}")
        # timeout to let developer track the ui changes
        await webpage.wait_for_timeout(5000)

        return changed

    except TimeoutException as e:
        print(f"Failed to fill in text into target {target}, exception: {e}")
        return False


async def get_element_metadata(element: Locator) -> Dict[str, Any]:
    """
    Fetches essential metadata from a single element handle in a single browser-side evaluation.

    This is more efficient than making multiple `await` calls for each attribute.
    """
    js_script = """
    el => {
        return {
            outer_html: el.outerHTML,
            inner_html: el.innerHTML,
            placeholder: el.getAttribute('placeholder'),
            aria_label: el.getAttribute('aria-label'),
            aria_describedby: el.getAttribute('aria-describedby'),
            label: el.labels?.[0]?.innerText
        }
    }
    """
    metadata = await element.evaluate(js_script)
    metadata["element"] = element  # Keep the handle for later actions
    return metadata



async def get_text_inputs(page: Page):
    """Returns list of metadata corresponding to input_candidates"""
    # A comprehensive selector for all common text-editable elements.
    # This combines type, role, and contenteditable attributes for a single, efficient query.
    TEXT_INPUT_SELECTOR = (
        "input[type='text'], input[type='password'], input[type='email'], input[type='search'], "
        "input[type='tel'], input[type='url'], input[type='number'], input[type='date'], input[type='time'], "
        "input[type='datetime-local'], input[type='month'], input[type='week'], input[type='color'], "
        "textarea, [role='textbox'], [contenteditable='true']"
    )

    all_input_locators = page.locator(TEXT_INPUT_SELECTOR)
    all_input_texts = await all_input_locators.all()

    # filter out invisible elements
    input_candidates = [
        locator
        for locator in all_input_texts
         if await locator.is_visible()
    ]

    if not input_candidates:
        print("No visible text input elements found.")
        return []

    # run .evaluate tasks at once using asyncio.gather
    tasks = [get_element_metadata(el) for el in input_candidates]
    element_data = await asyncio.gather(*tasks)

    print(f"Found {len(element_data)} visible text-editable elements.")
    return element_data


async def enter_input(
    candidate_idx, candidates, input_text: str, page: Page, workflow_id=None
) -> bool:
    if not (0 <= candidate_idx < len(candidates)):
        print("Invalid candidate index")
        return False
    
    try:
        el: Locator = candidates[candidate_idx]["element"]

        # Define a sequence of input strategies to attempt
        # This avoids the deeply nested try/except blocks ("arrowhead" anti-pattern)
        # Each strategy is a function that returns True on success.
        async def strategy_fill() -> bool:
            print("Attempting strategy: fill()")
            await el.scroll_into_view_if_needed()
            bounding_box = await el.bounding_box()
            if bounding_box is not None: 
                await page.mouse.click(bounding_box["x"]+ 5, (bounding_box["y"] + bounding_box["height"])/2 )
            await el.fill(input_text, timeout=INTERACTION_TIMEOUT_MS)
            return True

        async def strategy_force_fill() -> bool:
            print("Attempting strategy: fill(force=True)")
            await el.fill(input_text, force=True, timeout=INTERACTION_TIMEOUT_MS)
            return True

        async def strategy_type() -> bool:
            print("Attempting strategy: type()")
            await el.scroll_into_view_if_needed()
            bounding_box = await el.bounding_box()
            if bounding_box is not None: 
                await page.mouse.click(bounding_box["x"]+ 5, (bounding_box["y"] + bounding_box["height"])/2 )
            await el.type(input_text, delay=200) # Add a small delay to simulate human typing
            return True

        async def strategy_keyboard() -> bool:
            print("Attempting strategy: page.keyboard.type()")
            await el.focus(timeout=INTERACTION_TIMEOUT_MS)
            await page.keyboard.type(input_text, delay=50)
            return True

        strategies: List[Callable[[], Coroutine[Any, Any, bool]]] = [
            strategy_type,
            strategy_keyboard,
            strategy_fill,
            strategy_force_fill,
        ]

        # 3. Execute strategies until one succeeds
        success = False
        for attempt in strategies:
            try:
                await attempt()
                print("Successfully entered text into the element.")
                success = True
                break  # Exit the loop on first success
            except Exception as e:
                print(f"Strategy failed: {e.__class__.__name__}. Trying next strategy.")
        
        if not success:
            print("All input strategies failed for the target element.")
            return False
        else: 
            if workflow_id is not None:
                options = SelectorOptions()
                selectors = await options.create_options(locator=el)
                from db.workflows import Workflows

                workflow = Workflows()
                workflow.add_step(
                    id=workflow_id, step={"action": "text_input", "selector": selectors, "value": input_text}
                )
            await page.wait_for_load_state("networkidle")
            return True
        
    except Exception as e:
        print("Text input error: ", e)
        import traceback
        traceback.print_exc()
        return False