/**
 * @fileoverview
 * This file provides a factory function `createDomUtils` that returns a suite of DOM utility functions.
 * These helpers are responsible for caching, DOM traversal (like XPath), visibility checks, and complex
 * interactivity assessments.
 *
 * By using a factory pattern, we can inject shared state (like `debugMode` and `PERF_METRICS`)
 * into the helpers' closure, allowing them to perform stateful operations (like performance tracking)
 * without polluting the global scope.
 */

// This module is designed to be instantiated within a closure that provides debugMode and PERF_METRICS.
export function createDomUtils(debugMode, PERF_METRICS, measureDomOperation) {

    /**
     * Caches DOM properties to avoid expensive re-calculations.
     */
    const DOM_CACHE = {
        boundingRects: new WeakMap(),
        clientRects: new WeakMap(),
        computedStyles: new WeakMap(),
        clearCache: () => {
            DOM_CACHE.boundingRects = new WeakMap();
            DOM_CACHE.clientRects = new WeakMap();
            DOM_CACHE.computedStyles = new WeakMap();
        }
    };

    /**
     * Retrieves an element's bounding rectangle, using a cache to improve performance.
     */
    function getCachedBoundingRect(element) {
        if (!element) return null;
        if (DOM_CACHE.boundingRects.has(element)) {
            if (debugMode) PERF_METRICS.cacheMetrics.boundingRectCacheHits++;
            return DOM_CACHE.boundingRects.get(element);
        }
        if (debugMode) PERF_METRICS.cacheMetrics.boundingRectCacheMisses++;
        let rect;
        if (debugMode) {
            const start = performance.now();
            rect = element.getBoundingClientRect();
            const duration = performance.now() - start;
            PERF_METRICS.buildDomTreeBreakdown.domOperations.getBoundingClientRect += duration;
            PERF_METRICS.buildDomTreeBreakdown.domOperationCounts.getBoundingClientRect++;
        } else {
            rect = element.getBoundingClientRect();
        }
        if (rect) DOM_CACHE.boundingRects.set(element, rect);
        return rect;
    }

    /**
     * Retrieves an element's computed style, using a cache.
     */
    function getCachedComputedStyle(element) {
        if (!element) return null;
        if (DOM_CACHE.computedStyles.has(element)) {
            if (debugMode) PERF_METRICS.cacheMetrics.computedStyleCacheHits++;
            return DOM_CACHE.computedStyles.get(element);
        }
        if (debugMode) PERF_METRICS.cacheMetrics.computedStyleCacheMisses++;
        let style;
        if (debugMode) {
            const start = performance.now();
            style = window.getComputedStyle(element);
            const duration = performance.now() - start;
            PERF_METRICS.buildDomTreeBreakdown.domOperations.getComputedStyle += duration;
            PERF_METRICS.buildDomTreeBreakdown.domOperationCounts.getComputedStyle++;
        } else {
            style = window.getComputedStyle(element);
        }
        if (style) DOM_CACHE.computedStyles.set(element, style);
        return style;
    }

    /**
     * Retrieves an element's client rectangles, using a cache.
     */
    function getCachedClientRects(element) {
        if (!element) return null;
        if (DOM_CACHE.clientRects.has(element)) {
            if (debugMode) PERF_METRICS.cacheMetrics.clientRectsCacheHits++;
            return DOM_CACHE.clientRects.get(element);
        }
        if (debugMode) PERF_METRICS.cacheMetrics.clientRectsCacheMisses++;
        const rects = element.getClientRects();
        if (rects) DOM_CACHE.clientRects.set(element, rects);
        return rects;
    }

    // --- XPath ---

    /**
     * Calculates the 1-based index of an element among its siblings of the same tag.
     */
    const xpathCache = new WeakMap();
    function getElementPosition(currentElement) {
        if (!currentElement.parentElement) return 0;
        const tagName = currentElement.nodeName.toLowerCase();
        const siblings = Array.from(currentElement.parentElement.children).filter((sib) => sib.nodeName.toLowerCase() === tagName);
        if (siblings.length === 1) return 0;
        return siblings.indexOf(currentElement) + 1;
    }

    /**
     * Generates a unique XPath for a given element.
     */
    function getXPathTree(element, stopAtBoundary = true) {
        // early return if cache hit
        if (xpathCache.has(element)) return xpathCache.get(element);
        const segments = [];
        let currentElement = element;
        while (currentElement && currentElement.nodeType === Node.ELEMENT_NODE) {
            if (stopAtBoundary && (currentElement.parentNode instanceof ShadowRoot || currentElement.parentNode instanceof HTMLIFrameElement)) {
                break;
            }
            const position = getElementPosition(currentElement);
            const tagName = currentElement.nodeName.toLowerCase();
            const xpathIndex = position > 0 ? `[${position}]` : "";
            segments.unshift(`${tagName}${xpathIndex}`);
            currentElement = currentElement.parentNode;
        }
        const result = segments.join("/");
        xpathCache.set(element, result);
        return result;
    }

    // --- Visibility and Acceptance ---

    /**
     * Checks if an element is of a type that should be included in the DOM tree.
     * Filters out non-essential elements like <script> and <style>.
     */
    function isElementAccepted(element) {
        if (!element || !element.tagName) return false;
        const alwaysAccept = new Set(["body", "div", "main", "article", "section", "nav", "header", "footer"]);
        if (alwaysAccept.has(element.tagName.toLowerCase())) return true;
        const leafElementDenyList = new Set(["svg", "script", "style", "link", "meta", "noscript", "template"]);
        return !leafElementDenyList.has(element.tagName.toLowerCase());
    }

    /**
     * Checks if an element is visually rendered on the page (has non-zero dimensions and is not hidden).
     */
    function isElementVisible(element) {
        const style = getCachedComputedStyle(element);
        return element.offsetWidth > 0 && element.offsetHeight > 0 && style.visibility !== "hidden" && style.display !== "none";
    }

    /**
     * Checks if a text node is visible in the viewport.
     */
    function isTextNodeVisible(textNode, viewportExpansion) {
        try {
            if (viewportExpansion === -1) {
                const parentElement = textNode.parentElement;
                if (!parentElement) return false;
                try {
                    return parentElement.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
                } catch (e) {
                    const style = window.getComputedStyle(parentElement);
                    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                }
            }
            const range = document.createRange();
            range.selectNodeContents(textNode);
            const rects = range.getClientRects();
            if (!rects || rects.length === 0) return false;
            for (const rect of rects) {
                if (rect.width > 0 && rect.height > 0) {
                    if (!(rect.bottom < -viewportExpansion || rect.top > window.innerHeight + viewportExpansion || rect.right < -viewportExpansion || rect.left > window.innerWidth + viewportExpansion)) {
                        const parentElement = textNode.parentElement;
                        if (!parentElement) return false;
                        try {
                            return parentElement.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
                        } catch (e) {
                            const style = window.getComputedStyle(parentElement);
                            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                        }
                    }
                }
            }
            return false;
        } catch (e) {
            console.warn('Error checking text node visibility:', e);
            return false;
        }
    }

    /**
     * Determines if an element is the topmost element at its screen coordinates.
     */
    function isTopElement(element, viewportExpansion) {
        if (viewportExpansion === -1) return true;
        const rects = getCachedClientRects(element);
        if (!rects || rects.length === 0) return false;
        let isAnyRectInViewport = false;
        for (const rect of rects) {
            if (rect.width > 0 && rect.height > 0 && !(rect.bottom < -viewportExpansion || rect.top > window.innerHeight + viewportExpansion || rect.right < -viewportExpansion || rect.left > window.innerWidth + viewportExpansion)) {
                isAnyRectInViewport = true;
                break;
            }
        }
        if (!isAnyRectInViewport) return false;
        const centerX = rects[Math.floor(rects.length / 2)].left + rects[Math.floor(rects.length / 2)].width / 2;
        const centerY = rects[Math.floor(rects.length / 2)].top + rects[Math.floor(rects.length / 2)].height / 2;
        const shadowRoot = element.getRootNode();
        if (shadowRoot instanceof ShadowRoot) {
            try {
                const topEl = measureDomOperation(() => shadowRoot.elementFromPoint(centerX, centerY), 'elementFromPoint');
                let current = topEl;
                while (current && current !== shadowRoot) {
                    if (current === element) return true;
                    current = current.parentElement;
                }
                return false;
            } catch (e) { return true; }
        }
        try {
            const topEl = document.elementFromPoint(centerX, centerY);
            let current = topEl;
            while (current && current !== document.documentElement) {
                if (current === element) return true;
                current = current.parentElement;
            }
            return false;
        } catch (e) { return true; }
    }

    /**
     * Checks if an element is within the expanded viewport boundaries.
     */
    function isInExpandedViewport(element, viewportExpansion) {
        if (viewportExpansion === -1) return true;
        const rects = element.getClientRects();
        if (!rects || rects.length === 0) {
            const boundingRect = getCachedBoundingRect(element);
            if (!boundingRect || boundingRect.width === 0 || boundingRect.height === 0) return false;
            return !(boundingRect.bottom < -viewportExpansion || boundingRect.top > window.innerHeight + viewportExpansion || boundingRect.right < -viewportExpansion || boundingRect.left > window.innerWidth + viewportExpansion);
        }
        for (const rect of rects) {
            if (rect.width === 0 || rect.height === 0) continue;
            if (!(rect.bottom < -viewportExpansion || rect.top > window.innerHeight + viewportExpansion || rect.right < -viewportExpansion || rect.left > window.innerWidth + viewportExpansion)) {
                return true;
            }
        }
        return false;
    }

    // --- Interactivity ---

    /**
     * A fast, preliminary check to see if an element might be interactive.
     */
    function isInteractiveCandidate(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
        const tagName = element.tagName.toLowerCase();
        const interactiveElements = new Set(["a", "button", "input", "select", "textarea", "details", "summary", "label"]);
        if (interactiveElements.has(tagName)) return true;
        return element.hasAttribute("onclick") || element.hasAttribute("role") || element.hasAttribute("tabindex") || element.hasAttribute("aria-") || element.hasAttribute("data-action") || element.getAttribute("contenteditable") === "true";
    }

    /**
     * A comprehensive check to determine if an element is interactive, considering its tag,
     * style (cursor), attributes, and event listeners.
     */
    function isInteractiveElement(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
        const tagName = element.tagName.toLowerCase();
        const style = getCachedComputedStyle(element);
        const interactiveCursors = new Set(['pointer', 'move', 'text', 'grab', 'grabbing', 'cell', 'copy', 'alias', 'all-scroll', 'col-resize', 'context-menu', 'crosshair', 'e-resize', 'ew-resize', 'help', 'n-resize', 'ne-resize', 'nesw-resize', 'ns-resize', 'nw-resize', 'nwse-resize', 'row-resize', 's-resize', 'se-resize', 'sw-resize', 'vertical-text', 'w-resize', 'zoom-in', 'zoom-out']);
        if (interactiveCursors.has(style.cursor)) return true;
        const nonInteractiveCursors = new Set(['not-allowed', 'no-drop', 'wait', 'progress', 'initial', 'inherit']);
        const interactiveElements = new Set(["a", "button", "input", "select", "textarea", "details", "summary", "label", "option", "optgroup", "fieldset", "legend"]);
        if (interactiveElements.has(tagName)) {
            if (nonInteractiveCursors.has(style.cursor)) return false;
            if (element.hasAttribute('disabled') || element.getAttribute('disabled') === 'true' || element.getAttribute('disabled') === '') return false;
            if (element.hasAttribute('readonly')) return false;
            if (element.disabled || element.readOnly || element.inert) return false;
            return true;
        }
        if (element.getAttribute("contenteditable") === "true" || element.isContentEditable) return true;
        if (element.classList && (element.classList.contains("button") || element.classList.contains('dropdown-toggle') || element.getAttribute('data-index') || element.getAttribute('data-toggle') === 'dropdown' || element.getAttribute('aria-haspopup') === 'true')) return true;
        const role = element.getAttribute("role");
        const ariaRole = element.getAttribute("aria-role");
        const interactiveRoles = new Set(['button', 'menuitemradio', 'menuitemcheckbox', 'radio', 'checkbox', 'tab', 'switch', 'slider', 'spinbutton', 'combobox', 'searchbox', 'textbox', 'option', 'scrollbar']);
        if (interactiveRoles.has(role) || interactiveRoles.has(ariaRole)) return true;
        try {
            if (typeof getEventListeners === 'function') {
                const listeners = getEventListeners(element);
                const mouseEvents = ['click', 'mousedown', 'mouseup', 'dblclick'];
                for (const eventType of mouseEvents) {
                    if (listeners[eventType] && listeners[eventType].length > 0) return true;
                }
            }
            const commonMouseAttrs = ['onclick', 'onmousedown', 'onmouseup', 'ondblclick'];
            for (const attr of commonMouseAttrs) {
                if (element.hasAttribute(attr) || typeof element[attr] === 'function') return true;
            }
        } catch (e) { }
        return false;
    }

    /**
     * A heuristic check for elements that may be interactive but are not easily detected
     * by standard properties (e.g., a div with a click handler).
     */
    function isHeuristicallyInteractive(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
        if (!isElementVisible(element)) return false;
        const hasInteractiveAttributes = element.hasAttribute('role') || element.hasAttribute('tabindex') || element.hasAttribute('onclick') || typeof element.onclick === 'function';
        const hasInteractiveClass = /\b(btn|clickable|menu|item|entry|link)\b/i.test(element.className || '');
        const isInKnownContainer = Boolean(element.closest('button,a,[role="button"],.menu,.dropdown,.list,.toolbar'));
        const hasVisibleChildren = [...element.children].some(isElementVisible);
        const isParentBody = element.parentElement && element.parentElement.isSameNode(document.body);
        return (isInteractiveElement(element) || hasInteractiveAttributes || hasInteractiveClass) && hasVisibleChildren && isInKnownContainer && !isParentBody;
    }

    const DISTINCT_INTERACTIVE_TAGS = new Set(['a', 'button', 'input', 'select', 'textarea', 'summary', 'details', 'label', 'option']);
    const INTERACTIVE_ROLES = new Set(['button', 'link', 'menuitem', 'menuitemradio', 'menuitemcheckbox', 'radio', 'checkbox', 'tab', 'switch', 'slider', 'spinbutton', 'combobox', 'searchbox', 'textbox', 'listbox', 'option', 'scrollbar']);

    /**
     * Determines if an element represents a distinct interaction from its parent,
     * which is crucial for handling nested interactive elements.
     */
    function isElementDistinctInteraction(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
        const tagName = element.tagName.toLowerCase();
        const role = element.getAttribute('role');
        if (tagName === 'iframe') return true;
        if (DISTINCT_INTERACTIVE_TAGS.has(tagName) || (role && INTERACTIVE_ROLES.has(role))) return true;
        if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') return true;
        if (element.hasAttribute('data-testid') || element.hasAttribute('data-cy') || element.hasAttribute('data-test')) return true;
        if (element.hasAttribute('onclick') || typeof element.onclick === 'function') return true;
        if (isHeuristicallyInteractive(element)) return true;
        return false;
    }

    return {
        DOM_CACHE,
        getCachedBoundingRect,
        getCachedComputedStyle,
        getCachedClientRects,
        getXPathTree,
        isElementAccepted,
        isElementVisible,
        isTextNodeVisible,
        isTopElement,
        isInExpandedViewport,
        isInteractiveCandidate,
        isInteractiveElement,
        isElementDistinctInteraction
    };
} 