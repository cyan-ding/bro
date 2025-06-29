# function to input text

from patchright.async_api import Page


# returns list of metadata corresponding to input_candidates
async def get_text_input(page: Page):
    # 1. Typed input fields (textual + special types)
    typed_inputs = await page.locator(
        "input[type='text'], input[type='password'], input[type='email'], input[type='search'], "
        + "input[type='tel'], input[type='url'], input[type='number'], input[type='date'], input[type='time'], "
        + "input[type='datetime-local'], input[type='month'], input[type='week'], input[type='color']"
    ).all()

    # 2. Textareas
    textareas = await page.locator("textarea").all()

    # 3. ARIA role="textbox" (includes textareas and custom inputs)
    aria_textboxes = await page.get_by_role("textbox").all()

    # 4. Class-based selectors (common framework input classes)
    class_based_inputs = await page.locator(
        "[class*='input'], [class*='field'], [class*='form'], [class*='search'], [class*='textbox'], [class*='text-area']"
    ).all()

    # 5. Contenteditable elements (e.g., for rich text editors)
    editable_elements = await page.locator("[contenteditable='true']").all()

    input_candidates = list(
        set(
            typed_inputs
            + textareas
            + aria_textboxes
            + class_based_inputs
            + editable_elements
        )
    )

    element_data = []
    for el in input_candidates:
        html = await el.inner_html()
        placeholder = await el.get_attribute("placeholder")
        aria_label = await el.get_attribute("aria-label")
        aria_describedby = await el.get_attribute("aria-describedby")
        label = await el.evaluate("el => el.labels?.[0]?.innerText")  # linked <label>

        element_data.append(
            {
                "element": el,
                "html": html,
                "placeholder": placeholder,
                "aria_label": aria_label,
                "aria_describedby": aria_describedby,
                "label": label,
            }
        )

    return element_data


async def enter_input(llm_input, page: Page, site: str, input_text: str):
    try:
        # Get the current input candidates for this page
        input_candidates = await get_text_input(page)
        matched_candidates = []
        # Find matching input element
        matched_input = None
        for candidate_data in input_candidates:
            if (
                (candidate_data.get("html") == llm_input.get("html"))
                or (candidate_data.get("placeholder") == llm_input.get("placeholder"))
                or (candidate_data.get("aria_label") == llm_input.get("aria_label"))
                or (
                    candidate_data.get("aria_describedby")
                    == llm_input.get("aria_describedby")
                )
                or (candidate_data.get("label") == llm_input.get("label"))
            ):
                matched_element = candidate_data["element"]
                matched_input = matched_element
                matched_candidates.append(matched_element)

        if matched_input is None:
            print("No matching input element found")
            return

        # Try multiple strategies to fill the input
        for candidate in matched_candidates:
            try:
                # Strategy 1: Wait for element to be visible and try fill
                await candidate.wait_for(state="visible", timeout=5000)
                await candidate.scroll_into_view_if_needed()
                await candidate.click()
                await candidate.fill(input_text)
                print(
                    f"Successfully filled element: {await candidate.get_attribute('placeholder')}"
                )
                break
            except Exception:
                try:
                    await candidate.fill(input_text, force=True)
                    print(
                        f"Successfully filled element with force: {await candidate.get_attribute('placeholder')}"
                    )
                    break
                except Exception:
                    try:
                        await candidate.type(input_text)
                        print(
                            f"Successfully typed into element: {await candidate.get_attribute('placeholder')}"
                        )
                        break
                    except Exception:
                        await candidate.focus()
                        await page.keyboard.type(input_text)
                        print(
                            f"Successfully used keyboard input: {await candidate.get_attribute('placeholder')}"
                        )
                        break

        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=f"tools/actions/ss/{site}.png")

    except Exception as e:
        print("Text input error: ", e)
        import traceback

        traceback.print_exc()
