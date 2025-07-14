"""
This file provides utility functions for browser actions in Bro.
It includes selector generation logic for Playwright elements, to support robust workflow serialization.

# @file purpose: Defines utility functions for browser actions, including selector generation for workflow steps.
"""

import re
import asyncio
from patchright.async_api import Locator, Page, async_playwright
from actions.search import search


def sanitize_filename(name):
    """Sanitize filename to be safe for filesystem"""
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)

class SelectorOptions:
    """Wrapper class to contain all options, to be used in workflows"""
    def __init__(self):
        self.options = []
    
    async def create_options(self, locator: Locator):
        best_selector = await get_best_selector(locator)
        xpath_options = await get_xpath_options(locator)
        self.options = xpath_options.append(best_selector)
        return self.options
        


async def get_best_selector(element: Locator) -> str:
    """
    Generate a robust selector for a Playwright element.
    Tries id, name, aria-label, placeholder, data-testid, type+class, text for buttons/links, then tag+class.
    Returns a CSS selector string.
    """
    # Try id
    el_id = await element.get_attribute("id")
    if el_id:
        return f"#{el_id}"
    # Try name
    name = await element.get_attribute("name")
    if name:
        return f"[name='{name}']"
    # Try aria-label
    aria_label = await element.get_attribute("aria-label")
    if aria_label:
        return f"[aria-label='{aria_label}']"
    # Try placeholder
    placeholder = await element.get_attribute("placeholder")
    if placeholder:
        return f"[placeholder='{placeholder}']"
    # Try data-testid
    data_testid = await element.get_attribute("data-testid")
    if data_testid:
        return f"[data-testid='{data_testid}']"
    # Try type + class
    el_type = await element.get_attribute("type")
    el_class = await element.get_attribute("class")
    if el_type and el_class:
        first_class = el_class.split()[0]
        return f"[type='{el_type}'][class*='{first_class}']"
    # Try text content for buttons/links
    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    if tag in ["button", "a"]:
        text = await element.inner_text()
        if text and len(text.strip()) < 40:
            safe_text = text.strip().replace("'", "\\'")
            return f"{tag}:has-text('{safe_text}')"
    # Fallback: tag + first class
    if el_class:
        first_class = el_class.split()[0]
        return f"{tag}.{first_class}"
    # Last resort: just tag
    return tag


async def get_xpath(locator: Locator):
    return await locator.evaluate("""
        node => {
            function getXPath(node) {
                // If node has an ID, use it for a more specific XPath
                if (node.id && node.id.trim() !== '')
                    return '//*[@id="' + node.id + '"]';
                
                // If it's the body element
                if (node === document.body)
                    return '/html/body';
                
                // If it's the html element
                if (node === document.documentElement)
                    return '/html';
                
                // For other elements, build the path
                let ix = 0;
                let siblings = node.parentNode.childNodes;
                
                for (let i = 0; i < siblings.length; i++) {
                    let sibling = siblings[i];
                    if (sibling === node) {
                        let path = getXPath(node.parentNode) + '/' + node.tagName.toLowerCase();
                        // Only add index if there are multiple siblings of the same type
                        let sameTagSiblings = 0;
                        for (let j = 0; j < siblings.length; j++) {
                            if (siblings[j].nodeType === 1 && siblings[j].tagName === node.tagName) {
                                sameTagSiblings++;
                            }
                        }
                        if (sameTagSiblings > 1) {
                            path += '[' + (ix + 1) + ']';
                        }
                        return path;
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === node.tagName) {
                        ix++;
                    }
                }
            }
            return getXPath(node);
        }
    """)

async def get_xpath_options(locator: Locator):
    """Get multiple XPath options for an element, including the most specific ones"""
    return await locator.evaluate("""
        node => {
            const options = [];
            
            // Option 1: ID-based (most specific)
            if (node.id && node.id.trim() !== '') {
                options.push('//*[@id="' + node.id + '"]');
            }
            
            // Option 2: Class-based (if unique)
            if (node.className && node.className.trim() !== '') {
                const classes = node.className.split(' ').filter(c => c.trim() !== '');
                if (classes.length > 0) {
                    const classSelector = classes.map(c => 'contains(@class, "' + c + '")').join(' and ');
                    options.push('//' + node.tagName.toLowerCase() + '[' + classSelector + ']');
                }
            }
            
            // Option 3: Text-based (if has text content)
            if (node.textContent && node.textContent.trim() !== '') {
                const text = node.textContent.trim().substring(0, 50); // Limit text length
                options.push('//' + node.tagName.toLowerCase() + '[contains(text(), "' + text + '")]');
            }
            
            // Option 4: Full path (what we had before)
            function getFullXPath(node) {
                if (node === document.body)
                    return '/html/body';
                if (node === document.documentElement)
                    return '/html';
                
                let ix = 0;
                let siblings = node.parentNode.childNodes;
                
                for (let i = 0; i < siblings.length; i++) {
                    let sibling = siblings[i];
                    if (sibling === node) {
                        let path = getFullXPath(node.parentNode) + '/' + node.tagName.toLowerCase();
                        let sameTagSiblings = 0;
                        for (let j = 0; j < siblings.length; j++) {
                            if (siblings[j].nodeType === 1 && siblings[j].tagName === node.tagName) {
                                sameTagSiblings++;
                            }
                        }
                        if (sameTagSiblings > 1) {
                            path += '[' + (ix + 1) + ']';
                        }
                        return path;
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === node.tagName) {
                        ix++;
                    }
                }
            }
            
            options.push(getFullXPath(node));
            
            return options;
        }
    """)


class DOMChangeDetector:
    def __init__(self, page: Page):
        self.page = page

    async def detect_any_change(self, action_fn, timeout=5000):
        """The most robust method - catches ALL DOM changes including inputs"""
        # Inject comprehensive change detection
        await self.page.evaluate("""
            () => {
                window.changeDetected = false;
                window.changes = [];
                
                // Clean up any existing listeners
                if (window.cleanup) window.cleanup();
                
                const recordChange = (type, target, details = {}) => {
                    window.changeDetected = true;
                    window.changes.push({
                        type,
                        target: target.tagName,
                        timestamp: Date.now(),
                        ...details
                    });
                };
                
                // 1. DOM Mutations (structure changes)
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach(m => recordChange('mutation', m.target, {
                        mutationType: m.type,
                        attributeName: m.attributeName
                    }));
                });
                
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    characterData: true
                });
                
                // 2. Input Events (form changes)
                const inputHandler = (e) => recordChange('input', e.target, {
                    value: e.target.value,
                    inputType: e.target.type
                });
                
                // 3. Property Changes (direct value assignments)
                const propertyHandler = (e) => recordChange('property', e.target, {
                    property: e.type,
                    value: e.target.value
                });
                
                // Add all event listeners
                document.addEventListener('input', inputHandler, true);
                document.addEventListener('change', inputHandler, true);
                document.addEventListener('propertychange', propertyHandler, true);
                
                // Cleanup function
                window.cleanup = () => {
                    observer.disconnect();
                    document.removeEventListener('input', inputHandler, true);
                    document.removeEventListener('change', inputHandler, true);
                    document.removeEventListener('propertychange', propertyHandler, true);
                };
            }
        """)

        async def navigation_watcher():
            try:
                async with self.page.expect_navigation(
                    timeout=timeout
                ) as navigation_info:
                    await action_fn()
                if await navigation_info.value:
                    return "navigation"
            except TimeoutError:
                return None

        async def dom_change_watcher():
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout:
                try:
                    detected = await self.page.evaluate("window.changeDetected")
                    # extract changes if desired: await self.page.evalulate("windows.changes")
                    if detected:
                        return "dom"
                except Exception:
                    pass
                await asyncio.sleep(0.01)  # 10ms polling
            return None

        # Start both watchers concurrently, but only call action_fn ONCE
        nav_task = asyncio.create_task(navigation_watcher())
        dom_task = asyncio.create_task(dom_change_watcher())

        done, pending = await asyncio.wait(
            [nav_task, dom_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel the other task
        for task in pending:
            task.cancel()

        await self.page.evaluate("() => { if (window.cleanup) window.cleanup(); }")

        for task in done:
            result = task.result()
            if result == "navigation":
                return True, ["Detected navigation"]
            elif result == "dom":
                return True, ["Detected DOM mutation"]

        return False, []


# Simple usage
async def check_if_action_worked(page: Page, action_fn):
    """Returns True if the action caused any DOM changes"""
    detector = DOMChangeDetector(page)
    changed, details = await detector.detect_any_change(action_fn)
    return changed, details


async def test_detection():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = await search("https://github.com", browser)

        # Snapshot comparison
        async def test_action():
            # await page.fill("#hero_user_email", "email")
            await page.click(
                # dom change:
                # "xpath=/html/body/div[1]/div[3]/header/div/div[2]/div/nav/ul/li[1]/button"
                # navigation:
                "xpath=/html/body/div[1]/div[6]/main/react-app/div/div/div/section[1]/div[1]/div[5]/div/form/section/div/button"
            )

        # Run the action and DOM change detection
        page_changed, details = await check_if_action_worked(page, test_action)

        element_changes = page_changed

        if element_changes:
            print(details)
        else:
            print("No change detected")

        # wait a bit for developers to monitor browser
        await page.wait_for_timeout(5000)

async def test_get_xpath():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = await search("https://github.com", browser)
        
        # Test with the original XPath

        original_xpath = "/html/body/div[1]/div[3]/header/div/div[2]/div/div/div/a"
        locator = page.locator(f"xpath={original_xpath}")
        
        print("=== XPath Generation Test ===")        
        # Get the improved XPath
        xpath = await get_xpath(locator=locator)
        print(f"Generated XPath: {xpath}")
        
        # Get multiple XPath options
        xpath_options = await get_xpath_options(locator=locator)
        print(f"XPath Options: {xpath_options}")

        assert xpath == original_xpath
        

if __name__ == "__main__":
    asyncio.run(test_get_xpath())
