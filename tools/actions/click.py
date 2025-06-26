from patchright.async_api import Page


async def get_button(page: Page, site: str):
    # Get explicit links and buttons
    links = await page.get_by_role("link").all()
    buttons = await page.get_by_role("button").all()

    # Get divs and other elements that might be clickable
    clickable_divs = await page.locator(
        "div[onclick], div[data-click], div[class*='click'], div[class*='button'], div[class*='link'], div[class*='nav'], div[class*='menu'], div[class*='tab'], div[class*='card'], div[class*='item']"
    ).all()

    # Get elements with cursor pointer (often indicates clickable)
    pointer_elements = await page.locator(
        "[style*='cursor: pointer'], [style*='cursor:pointer'], [class*='cursor-pointer'], [class*='pointer']"
    ).all()

    # Get elements with click handlers
    click_handlers = await page.locator(
        "[onclick], [onmousedown], [onmouseup], [data-action], [data-click], [data-href], [data-url]"
    ).all()

    # Get anchor tags (links) that might be styled as buttons
    anchor_links = await page.locator("a[href]").all()

    # Get elements with button-like classes
    button_like = await page.locator(
        "[class*='btn'], [class*='button'], [class*='cta'], [class*='action'], [class*='submit'], [class*='primary'], [class*='secondary']"
    ).all()

    # Get any element with href attribute (not just anchor tags)
    href_elements = await page.locator("[href]").all()

    # Get image map areas (clickable regions on images)
    area_elements = await page.locator("area[href]").all()

    # Get images that have associated image maps
    image_maps = await page.locator("img[usemap]").all()

    # Get map elements
    map_elements = await page.locator("map").all()

    # Get orphaned area elements (not inside a map)
    orphaned_areas = await page.locator("area[href]").all()

    link_texts = []
    for link in links:
        label = await link.inner_text()
        if label.strip():
            link_texts.append(label)

    button_texts = []
    for button in buttons:
        label = await button.inner_text()
        if label.strip():
            button_texts.append(label)

    # Process clickable divs
    div_texts = []
    for div in clickable_divs:
        label = await div.inner_text()
        if label.strip():
            div_texts.append(label)

    # Process pointer elements
    pointer_texts = []
    for element in pointer_elements:
        label = await element.inner_text()
        if label.strip():
            pointer_texts.append(label)

    # Process click handlers
    handler_texts = []
    for element in click_handlers:
        label = await element.inner_text()
        if label.strip():
            handler_texts.append(label)

    # Process anchor links
    anchor_texts = []
    for anchor in anchor_links:
        label = await anchor.inner_text()
        if label.strip():
            anchor_texts.append(label)

    # Process button-like elements
    button_like_texts = []
    for element in button_like:
        label = await element.inner_text()
        if label.strip():
            button_like_texts.append(label)

    # Process elements with href attributes
    href_texts = []
    for element in href_elements:
        label = await element.inner_text()
        if label.strip():
            href_texts.append(label)

    # Process area elements (image map regions)
    area_texts = []
    area_info = []
    for area in area_elements:
        # Get alt text if available
        alt_text = await area.get_attribute("alt")
        href_value = await area.get_attribute("href")
        shape = await area.get_attribute("shape")
        coords = await area.get_attribute("coords")

        # Use alt text if available, otherwise use href as identifier
        display_text = alt_text if alt_text else f"Image region: {href_value}"
        area_texts.append(display_text)

        area_info.append(
            {"text": display_text, "href": href_value, "shape": shape, "coords": coords}
        )

    # Process orphaned area elements (areas without proper map structure)
    orphaned_area_texts = []
    orphaned_area_info = []
    for area in orphaned_areas:
        href_value = await area.get_attribute("href")
        shape = await area.get_attribute("shape")
        coords = await area.get_attribute("coords")

        # For orphaned areas, use the href as the identifier
        display_text = f"Orphaned area: {href_value}"
        orphaned_area_texts.append(display_text)

        orphaned_area_info.append(
            {"text": display_text, "href": href_value, "shape": shape, "coords": coords}
        )

    # Process map elements
    map_info = []
    for map_elem in map_elements:
        name = await map_elem.get_attribute("name")
        id_attr = await map_elem.get_attribute("id")
        map_info.append({"name": name, "id": id_attr})

    # Process image maps
    image_map_info = []
    for img in image_maps:
        src = await img.get_attribute("src")
        alt = await img.get_attribute("alt")
        usemap = await img.get_attribute("usemap")
        image_map_info.append({"src": src, "alt": alt, "usemap": usemap})

    # Remove duplicates and combine all clickable elements
    all_clickable = list(
        set(
            link_texts
            + button_texts
            + div_texts
            + pointer_texts
            + handler_texts
            + anchor_texts
            + button_like_texts
            + href_texts
            + area_texts
            + orphaned_area_texts
        )
    )

    await page.screenshot(path=f"./temp/{site}.png")
    await page.close()

    return {
        "links": link_texts,
        "buttons": button_texts,
        "clickable_divs": div_texts,
        "pointer_elements": pointer_texts,
        "click_handlers": handler_texts,
        "anchor_links": anchor_texts,
        "button_like": button_like_texts,
        "href_elements": href_texts,
        "area_elements": area_texts,
        "area_details": area_info,
        "orphaned_areas": orphaned_area_texts,
        "orphaned_area_details": orphaned_area_info,
        "map_elements": map_info,
        "image_maps": image_map_info,
        "all_clickable": all_clickable,
    }
