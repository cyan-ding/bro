from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright

# Example usage

listener_tracking_script = """
    window.__elementListenerData = {};
    let counter = 0;
    (function () {
        function track(el, type) {
            try {
                if (!el || !el.tagName) return;
                if (!el.dataset.listenerId) {
                    el.dataset.listenerId = counter++;
                }
                const key = el.outerHTML;
                window.__elementListenerData[key] = {
                    id: el.dataset.listenerId,
                    tag: el.tagName,
                    type: type,
                    html: key
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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_page()
        context.add_init_script(listener_tracking_script)
        context.goto("https://chatgpt.com")
        import time

        time.sleep(10)  # Pause for 5 seconds
        data = context.evaluate("Object.values(window.__elementListenerData || {})")

        print(data)
        for el in data:
            if el["html"]:
                html = el["html"]
                soup = BeautifulSoup(html, "html.parser")
                # Find element with data-placeholder="Ask anything"
                target = soup.find(attrs={"data-testid": "login-button"})
                if isinstance(target, Tag):
                    selector = f"[data-listener-id='{el['id']}']"
                    try:
                        print(target)
                        context.locator(selector).click()
                        with context.expect_navigation(timeout=5000) as navigation_info:
                            # Navigation occurred, wait for it to complete
                            navigation_info.value
                        break
                    except TimeoutError:
                        continue

        context.wait_for_load_state("networkidle")
        context.screenshot(path="vision/ss/screenshot.png")


if __name__ == "__main__":
    main()
