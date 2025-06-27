# function to input text
from patchright.async_api import Page

element_data = []


async def get_text_input(page: Page):
    # 1. Typed input fields (textual + special types)
    typed_inputs = await page.locator(
        "input[type='text'], input[type='password'], input[type='email'], input[type='search']"
        + "input[type='tel'], input[type='url'], input[type='number'], input[type='date'], input[type='time']"
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

    for el in input_candidates:
        html = await el.inner_html()
        placeholder = await el.get_attribute("placeholder")
        aria_label = await el.get_attribute("aria-label")
        aria_describedby = await el.get_attribute("aria-describedby")
        label = await el.evaluate("el => el.labels?.[0]?.innerText")  # linked <label>

        element_data.append(
            {
                "html": html,
                "placeholder": placeholder,
                "aria_label": aria_label,
                "aria_describedby": aria_describedby,
                "label": label,
            }
        )

    return element_data


async def enter_input(llm_input: str, page: Page, site: str):
    print("Placeholder")
