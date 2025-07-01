from playwright.sync_api import sync_playwright
import hashlib
import time

listener_tracking_script = """
    window.__elementListenerData = {};
    window.__listenerCounter = window.__listenerCounter || 0;
    (function () {
        function track(el, type) {
            try {
                if (!el || !el.tagName) return;
                if (!el.dataset.listenerId) {
                    el.dataset.listenerId = window.__listenerCounter++;
                }
                const key = el.dataset.listenerId;
                window.__elementListenerData[key] = {
                    id: key,
                    tag: el.tagName,
                    type: type,
                    html: el.outerHTML
                };
            } catch (_) {}
        }
        const origAddEventListener = Element.prototype.addEventListener;
        Element.prototype.addEventListener = function(type, listener, options) {
            track(this, type);
            return origAddEventListener.call(this, type, listener, options);
        };
        const origWindowAdd = window.addEventListener;
        window.addEventListener = function(type, listener, options) {
            track(window, type);
            return origWindowAdd.call(this, type, listener, options);
        };
    })();
"""


def get_dom_hash(page):
    # Get a hash of the page's HTML
    html = page.content()
    return hashlib.md5(html.encode("utf-8")).hexdigest()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.add_init_script(listener_tracking_script)
        page.goto("https://chatgpt.com")

        time.sleep(10)  # Pause for 5 seconds
        data = page.evaluate("Object.values(window.__elementListenerData || {})")
        for el in data:
            print(f"ID: {el.get('id')}")
            print(f"Tag: {el.get('tag')}")
            print(f"Type: {el.get('type')}")
            html = el.get("html", "")
            # Print only the first 100 characters of html for brevity
            print(f"HTML: {html[:200]}{'...' if len(html) > 200 else ''}")
            print("-" * 40)

        # for el in data:
        #     if el["html"]:
        #         html = el["html"]
        #         soup = BeautifulSoup(html, "html.parser")
        #         # Find element with data-placeholder="Ask anything"
        #         target = soup.find(attrs={"data-testid": "signup-button"})
        #         if isinstance(target, Tag):
        #             selector = f"[data-listener-id='{el['id']}'] >> [data-testid='signup-button']"
        #             try:
        #                 locator = page.locator(selector)
        #                 print(target)
        #                 locator.wait_for(state="visible", timeout=3000)
        #                 before_hash = get_dom_hash(page)
        #                 page.wait_for_timeout(500)
        #                 locator.click()
        #                 try:
        #                     page.expect_navigation(timeout=5000)
        #                     # Wait for DOM to change (with timeout)
        #                     timeout = 5  # seconds
        #                     start = time.time()
        #                     while time.time() - start < timeout:
        #                         after_hash = get_dom_hash(page)
        #                         if after_hash != before_hash:
        #                             print("DOM changed!")
        #                             page.wait_for_timeout(5000)
        #                             page.screenshot(path="vision/ss/screenshot.png")
        #                             return
        #                         else:
        #                             print("DOM did not change within timeout.")
        #                 except TimeoutError:
        #                     print(traceback.print_exc())
        #                     locator.click()
        #             except TimeoutError:
        #                 continue


if __name__ == "__main__":
    main()
