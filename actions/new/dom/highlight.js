/**
 * @fileoverview
 * This file provides a factory function `createHighlightUtils` that returns utilities for visually
 * highlighting elements on the page. It handles the creation of overlays, labels, and the logic
 * for updating their positions on scroll and resize events.
 *
 * This approach encapsulates all highlight-related DOM manipulation and passes in timing functions
 * (`pushTiming`, `popTiming`) to integrate with performance measurement.
 */

export function createHighlightUtils(pushTiming, popTiming) {

    const HIGHLIGHT_CONTAINER_ID = "playwright-highlight-container";

    /**
     * Highlights a single element with a colored overlay and a numbered label.
     * Manages the dynamic updates of the highlight's position.
     * @param {Element} element The DOM element to highlight.
     * @param {number} index The highlight index number to display.
     * @param {Element|null} parentIframe The iframe containing the element, if any.
     * @returns {number} The time taken to highlight the element.
     */
    function highlightElement(element, index, parentIframe = null) {
        pushTiming('highlighting');
        if (!element) return 0;
        const overlays = [];
        let label = null;
        let labelWidth = 20, labelHeight = 16;
        let cleanupFn = null;

        try {
            // make a container for all highlights to easily delete them all at once
            let container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
            if (!container) {
                container = document.createElement("div");
                container.id = HIGHLIGHT_CONTAINER_ID;
                Object.assign(container.style, { position: "fixed", pointerEvents: "none", top: "0", left: "0", width: "100%", height: "100%", zIndex: "2147483640", backgroundColor: 'transparent' });
                document.body.appendChild(container);
            }
            // early return if no children
            const rects = element.getClientRects();
            if (!rects || rects.length === 0) return 0;

            // determine color of box based on index
            const colors = ["#FF0000", "#00FF00", "#0000FF", "#FFA500", "#800080", "#008080", "#FF69B4", "#4B0082", "#FF4500", "#2E8B57", "#DC143C", "#4682B4"];
            const baseColor = colors[index % colors.length];
            const backgroundColor = baseColor + "1A";

            // get offset of iframe if any
            let iframeOffset = { x: 0, y: 0 };
            if (parentIframe) {
                const iframeRect = parentIframe.getBoundingClientRect();
                iframeOffset = { x: iframeRect.left, y: iframeRect.top };
            }
            // use fragment as a container to allow for one append call (expensive)
            // start by adding an empty div with color styles for each child in the element
            const fragment = document.createDocumentFragment();
            for (const rect of rects) {
                if (rect.width === 0 || rect.height === 0) continue;
                const overlay = document.createElement("div");
                Object.assign(overlay.style, { position: "fixed", border: `2px solid ${baseColor}`, backgroundColor, pointerEvents: "none", boxSizing: "border-box", top: `${rect.top + iframeOffset.y}px`, left: `${rect.left + iframeOffset.x}px`, width: `${rect.width}px`, height: `${rect.height}px` });
                fragment.appendChild(overlay);
                overlays.push({ element: overlay, initialRect: rect });
            }
            // only add label to first child
            const firstRect = rects[0];
            label = document.createElement("div");
            Object.assign(label.style, { position: "fixed", background: baseColor, color: "white", padding: "1px 4px", borderRadius: "4px", fontSize: `${Math.min(12, Math.max(8, firstRect.height / 2))}px` });
            label.textContent = index;
            // calculate label dimensions
            labelWidth = label.offsetWidth > 0 ? label.offsetWidth : labelWidth;
            labelHeight = label.offsetHeight > 0 ? label.offsetHeight : labelHeight;
            let labelTop = firstRect.top + iframeOffset.y + 2;
            let labelLeft = firstRect.left + iframeOffset.x + firstRect.width - labelWidth - 2;
            if (firstRect.width < labelWidth + 4 || firstRect.height < labelHeight + 4) {
                labelTop = firstRect.top + iframeOffset.y - labelHeight - 2;
                labelLeft = firstRect.left + iframeOffset.x + firstRect.width - labelWidth;
                if (labelLeft < iframeOffset.x) labelLeft = firstRect.left + iframeOffset.x;
            }
            // add index label onto div
            Object.assign(label.style, { top: `${Math.max(0, Math.min(labelTop, window.innerHeight - labelHeight))}px`, left: `${Math.max(0, Math.min(labelLeft, window.innerWidth - labelWidth))}px` });
            fragment.appendChild(label);

            // hook to update box coords when scrolling
            const updatePositions = () => {
                const newRects = element.getClientRects();
                let newIframeOffset = { x: 0, y: 0 };
                if (parentIframe) {
                    const iframeRect = parentIframe.getBoundingClientRect();
                    newIframeOffset = { x: iframeRect.left, y: iframeRect.top };
                }
                // if element is still on the screen (newRects.length > 0), update box
                overlays.forEach((overlayData, i) => {
                    if (i < newRects.length) {
                        const newRect = newRects[i];
                        Object.assign(overlayData.element.style, { top: `${newRect.top + newIframeOffset.y}px`, left: `${newRect.left + newIframeOffset.x}px`, width: `${newRect.width}px`, height: `${newRect.height}px`, display: (newRect.width === 0 || newRect.height === 0) ? 'none' : 'block' });
                    } else {
                        overlayData.element.style.display = 'none';
                    }
                });
                // hide boxes that are no longer on the screen
                if (newRects.length < overlays.length) {
                    for (let i = newRects.length; i < overlays.length; i++) {
                        overlays[i].element.style.display = 'none';
                    }
                }
                // If the label exists and the element is still visible (has rects), update its position
                if (label && newRects.length > 0) {
                    const firstNewRect = newRects[0];
                    // Default: place label inside the top-right corner of the box, with 2px padding
                    let newLabelTop = firstNewRect.top + newIframeOffset.y + 2;
                    let newLabelLeft = firstNewRect.left + newIframeOffset.x + firstNewRect.width - labelWidth - 2;
                    // If the box is too small to fit the label inside (with 4px margin), move label above the box
                    if (firstNewRect.width < labelWidth + 4 || firstNewRect.height < labelHeight + 4) {
                        // Place label above the box, with a 2px gap
                        newLabelTop = firstNewRect.top + newIframeOffset.y - labelHeight - 2;
                        // Align label with the right edge of the box
                        newLabelLeft = firstNewRect.left + newIframeOffset.x + firstNewRect.width - labelWidth;
                        // If label would go off the left edge, snap it to the left edge of the box
                        if (newLabelLeft < newIframeOffset.x) newLabelLeft = firstNewRect.left + newIframeOffset.x;
                    }
                    // Clamp label position to stay within the viewport
                    Object.assign(label.style, {
                        top: `${Math.max(0, Math.min(newLabelTop, window.innerHeight - labelHeight))}px`,
                        left: `${Math.max(0, Math.min(newLabelLeft, window.innerWidth - labelWidth))}px`,
                        display: 'block'
                    });
                } else if (label) {
                    // Hide label if element is not visible
                    label.style.display = 'none';
                }
            };
            // wrapper function to delay function calls
            const throttleFunction = (func, delay) => {
                let lastCall = 0;
                return (...args) => {
                    const now = performance.now();
                    if (now - lastCall < delay) return;
                    lastCall = now;
                    func(...args);
                };
            };
            // add event listeners to move boxes when scrolling and resizing
            const throttledUpdatePositions = throttleFunction(updatePositions, 16);
            window.addEventListener('scroll', throttledUpdatePositions, true);
            window.addEventListener('resize', throttledUpdatePositions);

            cleanupFn = () => {
                window.removeEventListener('scroll', throttledUpdatePositions, true);
                window.removeEventListener('resize', throttledUpdatePositions);
                overlays.forEach(overlay => overlay.element.remove());
                if (label) label.remove();
            };
            // add fragment containing label + colored boxes to container
            container.appendChild(fragment);
            return popTiming('highlighting');
        
        } finally {
            popTiming('highlighting');
            if (cleanupFn) {
                (window._highlightCleanupFunctions = window._highlightCleanupFunctions || []).push(cleanupFn);
            }
        }
    }

    /**
     * Removes all highlight overlays and their associated event listeners from the page at once.
     */
    function cleanupHighlights() {
        if (window._highlightCleanupFunctions) {
            window._highlightCleanupFunctions.forEach(fn => fn());
            window._highlightCleanupFunctions = [];
        }
        const container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
        if (container) container.remove();
    }

    return { highlightElement, cleanupHighlights };
} 