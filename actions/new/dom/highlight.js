/**
 * @fileoverview
 * This file provides a factory function `createHighlightUtils` that returns utilities for visually
 * highlighting elements on the page. It handles the creation of overlays, labels, and the logic
 * for updating their positions on scroll and resize events.
 *
 * This approach encapsulates all highlight-related DOM manipulation and passes in timing functions
 * (`pushTiming`, `popTiming`) to integrate with performance measurement.
 */

export function createHighlightUtils(pushTiming, popTiming, getXPathTree) {

    const HIGHLIGHT_CONTAINER_ID = "playwright-highlight-container";
    
    // Array to track all highlighted elements
    const highlightedElements = [];

    /**
     * Extracts additional information about an element for tracking purposes.
     * @param {Element} element The DOM element to extract info from.
     * @returns {Object} Object containing aria-path, text content, and other relevant info.
     */
    function extractElementInfo(element) {
        const info = {
            ariaLabel: element.getAttribute('aria-label') || null,
            ariaLabelledby: element.getAttribute('aria-labelledby') || null,
            ariaDescribedby: element.getAttribute('aria-describedby') || null,
            role: element.getAttribute('role') || null,
            title: element.getAttribute('title') || null,
            placeholder: element.getAttribute('placeholder') || null,
            textContent: element.textContent?.trim().substring(0, 100) || null, // Limit to 100 chars
            id: element.id || null,
            className: element.className || null,
            type: element.getAttribute('type') || null,
            value: element.value || null,
            href: element.href || null,
            src: element.src || null,
            alt: element.getAttribute('alt') || null
        };
        
        // Remove null values to keep the object clean
        return Object.fromEntries(
            Object.entries(info).filter(([_, value]) => value !== null)
        );
    }

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
            // Track the highlighted element
            const elementInfo = {
                xpath: getXPathTree(element),
                tag: element.tagName.toLowerCase(),
                index: index,
                info: extractElementInfo(element)
            };
            highlightedElements.push(elementInfo);

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
                Object.assign(overlay.style, {
                    position: "fixed", border: `2px solid ${baseColor}`,
                    backgroundColor, pointerEvents: "none", boxSizing: "border-box",
                    top: `${rect.top + iframeOffset.y}px`, left: `${rect.left + iframeOffset.x}px`,
                    width: `${rect.width}px`, height: `${rect.height}px`
                });
                fragment.appendChild(overlay);
                overlays.push({ element: overlay, initialRect: rect });
            }
            // only add label to first child
            const firstRect = rects[0];
            label = document.createElement("div");
            // all attributes should scale with overlay size

            // label = box + index number
            // keeps font size between 8 and 12.
            Object.assign(label.style, {
                position: "fixed", background: baseColor, color: "white",
                padding: "1px 4px", borderRadius: "4px", fontSize: `${Math.min(12, Math.max(8, firstRect.height / 2))}px`
            });
            label.textContent = index;
            // calculate label dimensions
            // if too small, resort to defaults; width 20, height 16
            labelWidth = label.offsetWidth > 0 ? label.offsetWidth : labelWidth;
            labelHeight = label.offsetHeight > 0 ? label.offsetHeight : labelHeight;
            // calculate paddings for box relative to the bounding rect
            let labelTop = firstRect.top + iframeOffset.y + 2;
            let labelLeft = firstRect.left + iframeOffset.x + firstRect.width - labelWidth - 2;
            // if label is too small, move it above the box
            if (firstRect.width < labelWidth + 4 || firstRect.height < labelHeight + 4) {
                labelTop = firstRect.top + iframeOffset.y - labelHeight - 2;
                labelLeft = firstRect.left + iframeOffset.x + firstRect.width - labelWidth;
                if (labelLeft < iframeOffset.x) labelLeft = firstRect.left + iframeOffset.x;
            }
            // add index label onto div
            Object.assign(label.style, {
                top: `${Math.max(0, Math.min(labelTop, window.innerHeight - labelHeight))}px`,
                left: `${Math.max(0, Math.min(labelLeft, window.innerWidth - labelWidth))}px`
            });
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
                        Object.assign(overlayData.element.style, {
                            top: `${newRect.top + newIframeOffset.y}px`,
                            left: `${newRect.left + newIframeOffset.x}px`, width: `${newRect.width}px`,
                            height: `${newRect.height}px`, display: (newRect.width === 0 || newRect.height === 0)
                                ? 'none' : 'block'
                        });
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

            // function to clean up event listeners for the given element
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
                // add to global array of cleanup functions for the given web page
                (window._highlightCleanupFunctions = window._highlightCleanupFunctions || []).push(cleanupFn);
            }
        }
    }

    /**
     * Highlights interactive elements in the current viewport using pre-indexed positions.
     * 
     * @param {Map} interactiveElementsByPosition - Map of grid Y coordinates to arrays of element info
     * @param {Object} viewportInfo - Viewport information { scrollY, innerHeight }
     * @param {number} gridSize - Size of the position grid (default: 100)
     * @param {boolean} debugMode - Whether to log debug information
     * @returns {number} Number of elements highlighted
     */
    function highlightElementsInViewport(interactiveElementsByPosition, viewportInfo, gridSize = 100, debugMode = false) {
        const { scrollY, innerHeight } = viewportInfo;
        const viewportTop = scrollY;
        const viewportBottom = scrollY + innerHeight;
        
        // Calculate which grid sections are in viewport
        const startGridY = Math.floor(viewportTop / gridSize);
        const endGridY = Math.floor(viewportBottom / gridSize);
        
        const elementsToHighlight = [];
        
        // Collect all interactive elements in viewport
        for (let gridY = startGridY; gridY <= endGridY; gridY++) {
            const elementsInGrid = interactiveElementsByPosition.get(gridY);
            if (!elementsInGrid) continue;
            
            for (const elementInfo of elementsInGrid) {
                const { rect, element, nodeData } = elementInfo;
                
                // Check if element is actually in current viewport
                if (rect.bottom >= viewportTop && rect.top <= viewportBottom) {
                    elementsToHighlight.push(elementInfo);
                }
            }
        }
        
        // Sort by vertical position for consistent highlighting order
        elementsToHighlight.sort((a, b) => a.rect.top - b.rect.top);
        
        // Clear existing highlights
        cleanupHighlights();
        
        // Highlight elements
        elementsToHighlight.forEach((elementInfo, index) => {
            const { element, nodeData } = elementInfo;
            highlightElement(element, nodeData.highlightIndex || index);
        });
        
        if (debugMode) {
            console.log(`Highlighted ${elementsToHighlight.length} elements in viewport`);
        }
        
        return elementsToHighlight.length;
    }

    /**
     * Creates a throttled scroll handler for efficient viewport highlighting.
     * 
     * @param {Map} interactiveElementsByPosition - Map of grid Y coordinates to arrays of element info
     * @param {number} gridSize - Size of the position grid (default: 100)
     * @param {boolean} debugMode - Whether to log debug information
     * @returns {Function} Throttled scroll handler function
     */
    function createScrollHandler(interactiveElementsByPosition, gridSize = 100, debugMode = false) {
        let lastScrollY = window.scrollY;
        let lastCall = 0;
        const throttleDelay = 100; // 100ms throttle
        
        return function handleScroll() {
            const now = performance.now();
            if (now - lastCall < throttleDelay) return;
            lastCall = now;
            
            const currentScrollY = window.scrollY;
            
            // Only re-highlight if scroll position changed significantly
            if (Math.abs(currentScrollY - lastScrollY) < 50) return;
            
            // Highlight elements in new viewport
            const viewportInfo = {
                scrollY: currentScrollY,
                innerHeight: window.innerHeight
            };
            
            highlightElementsInViewport(interactiveElementsByPosition, viewportInfo, gridSize, debugMode);
            
            lastScrollY = currentScrollY;
        };
    }

    /**
     * Removes all highlight overlays and their associated event listeners from the page 
     */
    function cleanupHighlights() {
        if (window._highlightCleanupFunctions) {
            window._highlightCleanupFunctions.forEach(fn => fn());
            window._highlightCleanupFunctions = [];
        }
        const container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
        if (container) container.remove();
        
        // Clear the tracking array
        highlightedElements.length = 0;
    }

    /**
     * Gets the array of currently highlighted elements.
     * @returns {Array} Array of highlighted element objects.
     */
    function getHighlightedElements() {
        return [...highlightedElements];
    }


    return { 
        highlightElement, 
        cleanupHighlights, 
        getHighlightedElements,
        highlightElementsInViewport,
        createScrollHandler
    };
} 