/**
 * @fileoverview
 * This is the main entry point for the DOM tree analysis script.
 *
 * It orchestrates the entire process by:
 * 1. Importing factory functions from the other modules (`dom_utils`, `metrics`, `highlight`).
 * 2. Instantiating the helpers, creating a shared context for stateful operations like performance tracking.
 * 3. Executing the recursive DOM tree traversal (`buildTreeRecursive`).
 * 4. Handling the final metrics processing and returning the result.
 *
 * This modular design improves readability and maintainability by separating concerns into distinct files.
 */

import { createDomUtils } from './dom_utils.js';
import { createMetrics } from './metrics.js';
import { createHighlightUtils } from './highlight.js';

/**
 * Builds a DOM tree representation starting from the document body.
 *
 * This function serves as the main entry point for DOM analysis. It initializes
 * all required utilities (DOM helpers, metrics, highlighting), manages shared state,
 * and recursively traverses the DOM to construct a tree structure. The result includes
 * a mapping of node IDs to their data, and optionally, performance metrics if debug mode is enabled.
 *
 * @param {Object} args - Configuration options for the DOM tree builder.
 * @param {boolean} args.doHighlightElements - Whether to visually highlight interactive elements.
 * @param {boolean} args.debugMode - Enables detailed performance metrics and logging.
 * @param {number} args.overlapThreshold - Threshold for area overlap detection (0.7 = 70%)
 * @param {boolean} args.indexByPosition - Whether to index interactive elements by position for efficient viewport highlighting.
 *
 * @returns {Object} An object containing the root node ID, a map of all node data, and (if debugMode) performance metrics.
 *
 * @example
 * const result = buildDomTree({ doHighlightElements: true, debugMode: false });
 * // result: { rootId: "0", map: { "0": {...}, ... } }
 */
export default function buildDomTree(args = {
    doHighlightElements: true,
    debugMode: true,
    overlapThreshold: 0.7, // Threshold for area overlap detection (0.7 = 70%)
    indexByPosition: false, // Whether to index interactive elements by position
}) {
    const { doHighlightElements, debugMode, overlapThreshold, indexByPosition } = args;

    // --- Instantiate helpers with shared state ---
    const { PERF_METRICS, measureDomOperation, postProcessMetrics, pushTiming, popTiming } = createMetrics(debugMode);
    const domUtils = createDomUtils(debugMode, PERF_METRICS, measureDomOperation);
    const { highlightElement, cleanupHighlights, getHighlightedElements, highlightElementsInViewport, createScrollHandler } = createHighlightUtils(pushTiming, popTiming, domUtils.getXPathTree);

    // --- Main state ---
    let highlightIndex = 0;
    const DOM_HASH_MAP = {};
    const ID = { current: 0 };

    // --- Position-based indexing for efficient viewport highlighting ---
    const INTERACTIVE_ELEMENTS_BY_POSITION = new Map(); // y-coordinate -> array of elements
    const POSITION_GRID_SIZE = 100; // Group elements by 100px vertical sections

    // --- Core Logic ---
    /**
     * Handles the highlighting logic for interactive elements, including area overlap detection.
     * 
     * @param {Object} nodeData - The data object for the current node.
     * @param {Element} node - The DOM element to potentially highlight.
     * @param {Element|null} parentIframe - The parent iframe element if inside an iframe.
     * @param {boolean} highlightedAncestor - If the element has a highlighted ancestor, null if no ancestor.
     * @returns {Element|null} The element if it was highlighted, null otherwise.
     */
    function handleHighlighting(nodeData, node, parentIframe, highlightedAncestor = null) {
        if (!nodeData.isInteractive) return highlightedAncestor;

        // only highlight if no highlighted ancestor or if its distinct
        if (!highlightedAncestor || domUtils.isElementDistinctInteraction(node)) {
            // Additional safeguard: if parent is highlighted, require stronger evidence of distinctness
            if (highlightedAncestor) {
                const tagName = node.tagName.toLowerCase();
                const isWrapperTag = ['div', 'span', 'section', 'article'].includes(tagName);

                // For wrapper tags, require explicit interactive properties
                if (isWrapperTag) {
                    const hasExplicitInteractivity = node.hasAttribute('onclick') || node.hasAttribute('role') ||
                        node.hasAttribute('tabindex') || /\b(btn|clickable)\b/i.test(node.className || '');
                    if (!hasExplicitInteractivity) return highlightedAncestor;
                }

                // Area overlap check: prevent highlighting if element overlaps significantly with highlighted ancestor
                const nodeRect = domUtils.getCachedBoundingRect(node);
                if (nodeRect) {
                    const parentRect = domUtils.getCachedBoundingRect(highlightedAncestor);
                    if (parentRect) {
                        const xOverlap = Math.max(0, Math.min(nodeRect.right, parentRect.right) - Math.max(nodeRect.left, parentRect.left));
                        const yOverlap = Math.max(0, Math.min(nodeRect.bottom, parentRect.bottom) - Math.max(nodeRect.top, parentRect.top));
                        const overlapArea = xOverlap * yOverlap;
                        const overlapRatio = overlapArea / Math.max(nodeRect.width * nodeRect.height, parentRect.width * parentRect.height);
                        if (overlapRatio > overlapThreshold) {
                            return highlightedAncestor;
                        }
                    }
                }
            }

            nodeData.highlightIndex = highlightIndex++;
            if (doHighlightElements) {
                const time = highlightElement(node, nodeData.highlightIndex, parentIframe) || 0;
                if (debugMode) PERF_METRICS.timings.highlightElement += time;
                // return element if successful highlight -- this is to signal that children should not be highlighted.
                return node;
            }
        }
        return highlightedAncestor;
    }

    /**
     * Recursively traverses the DOM tree and builds a serializable representation of each node.
     * Handles element filtering, visibility, highlighting, and special cases such as iframes, shadow DOM, and text nodes.
     *
     * @param {Node} node - The current DOM node to process.
     * @param {Element|null} [parentIframe=null] - The parent iframe element if inside an iframe, otherwise null.
     * @param {Element|null} [highlightedAncestor=null] - The parent node that was highlighted, to avoid redundant highlights.
     * @returns {string|null} The unique ID of the processed node in the DOM_HASH_MAP, or null if the node is skipped.
     *
     * @remarks
     * - Skips nodes that are not elements or text, or are not visible/accepted.
     * - Handles text nodes, shadow DOM, and content-editable regions.
     * - Applies highlighting logic if enabled.
     */
    function buildTreeRecursive(node, parentIframe = null, highlightedAncestor = null, isInViewport = false) {
        if (debugMode) {
            PERF_METRICS.nodeMetrics.totalNodes++;
            PERF_METRICS.calls.buildDomTree++;
        }
        if (
            !node ||
            node.id === 'playwright-highlight-container' ||
            ![Node.ELEMENT_NODE, Node.TEXT_NODE, Node.DOCUMENT_FRAGMENT_NODE].includes(node.nodeType)
        ) {
            if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
            return null;
        }
        // process body node
        if (node === document.body) {
            const nodeData = { tagName: 'body', attributes: {}, xpath: '/body', children: [] };
            for (const child of node.childNodes) {
                const domElement = buildTreeRecursive(child, parentIframe, highlightedAncestor, isInViewport);
                if (domElement) nodeData.children.push(domElement);
            }
            const id = `${ID.current++}`;
            DOM_HASH_MAP[id] = nodeData;
            if (debugMode) PERF_METRICS.nodeMetrics.processedNodes++;
            return id;
        }
        // process text node (text content inside of another element)
        if (node.nodeType === Node.TEXT_NODE) {
            const textContent = node.textContent.trim();
            // skip nodes with empty text
            if (!textContent) {
                if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
                return null;
            }

            const id = `${ID.current++}`;
            DOM_HASH_MAP[id] = { type: "TEXT_NODE", text: textContent, isVisible: domUtils.isTextNodeVisible(node) };
            if (debugMode) PERF_METRICS.nodeMetrics.processedNodes++;
            return id;
        }
        // check whether element is of accepted type
        if (!domUtils.isElementAccepted(node)) {
            if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
            return null;
        }
        // tagname will be null for shadow nodes, so don't call .toLowerCase()
        const nodeData = {
            tagName: node.tagName ? node.tagName.toLowerCase() : null,
            attributes: {},
            xpath: node.tagName ? domUtils.getXPathTree(node, true) : null,
            children: [],
            // other potential node data to populate conditionally
            // isInteractive: false,
            // isVisible: false,
            // highlightIndex: -1,
            // shadowRoot: false,
        };
        // only populate attributes if element is interactive
        if (domUtils.isInteractiveCandidate(node) || nodeData.tagName === 'iframe') {
            const attributeNames = node.getAttributeNames?.() || [];
            for (const name of attributeNames) {
                nodeData.attributes[name] = node.getAttribute(name);
            }
        }
        // populate isVisible, isInteractive attributes of nodeData
        let newHighlightedAncestor = null;
        nodeData.isVisible = domUtils.isElementVisible(node); // this is the only visibility check
        if (nodeData.isVisible) {
            nodeData.isInteractive = domUtils.isInteractiveElement(node);
            // mark element to be highlighted (so that children are not highlighted)
            newHighlightedAncestor = handleHighlighting(nodeData, node, parentIframe, highlightedAncestor);
        }
        
        // Index element by position if enabled and interactive
        if (indexByPosition && nodeData.isInteractive) {
            domUtils.indexElementByPosition(node, nodeData, INTERACTIVE_ELEMENTS_BY_POSITION, POSITION_GRID_SIZE);
        }
        
        // Check for special types of nodes with internal structures, recurse through those
        const tagName = nodeData.tagName;
        // for iframes
        if (tagName === "iframe") {
            try {
                const iframeDoc = node.contentDocument || node.contentWindow?.document;
                if (iframeDoc) {
                    for (const child of iframeDoc.childNodes) {
                        const domElement = buildTreeRecursive(child, node, newHighlightedAncestor);
                        if (domElement) nodeData.children.push(domElement);
                    }
                }
            } catch (e) { console.warn("Unable to access iframe:", e); }
        } else if (node.shadowRoot) {
            // for shadow DOM elements that have internal structure
            nodeData.shadowRoot = true;
            for (const child of node.shadowRoot.childNodes) {
                const domElement = buildTreeRecursive(child, parentIframe, newHighlightedAncestor);
                if (domElement) nodeData.children.push(domElement);
            }
            for (const child of node.children) {
                const domElement = buildTreeRecursive(child, parentIframe, newHighlightedAncestor);
                if (domElement) nodeData.children.push(domElement);
            }
        } else {
            // for all other nodes, recurse through children
            for (const child of node.children) {
                const domElement = buildTreeRecursive(child, parentIframe, newHighlightedAncestor);
                if (domElement) nodeData.children.push(domElement);
            }
        }
    
        // Skip empty anchor tags only if they have no dimensions and no children 
        // -- Many websites include empty <a> tags for layout, tracking, or JS hooks.
        if (tagName === 'a' && nodeData.children.length === 0 && !nodeData.attributes.href) {
            const rect = domUtils.getCachedBoundingRect(node);
            // skip if anchor has no size
            const hasSize = (rect && rect.width > 0 && rect.height > 0) || (node.offsetWidth > 0 || node.offsetHeight > 0);
            if (!hasSize) {
                if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
                return null;
            }
        }

        const id = `${ID.current++}`;
        DOM_HASH_MAP[id] = nodeData;
        if (debugMode) PERF_METRICS.nodeMetrics.processedNodes++;
        return id;
    }

    // --- Execution ---
    domUtils.DOM_CACHE.clearCache();
    if (window._highlightCleanupFunctions) cleanupHighlights();

    const wrappedBuildTree = measureDomOperation(buildTreeRecursive, 'buildDomTree');
    PERF_METRICS.calls.buildDomTree--; // remove this extra call to measureDomOperation
    const rootId = wrappedBuildTree(document.body);

    postProcessMetrics();
    
    // Set up scroll handler if position indexing is enabled
    if (indexByPosition) {
        const scrollHandler = createScrollHandler(INTERACTIVE_ELEMENTS_BY_POSITION, POSITION_GRID_SIZE, debugMode);
        window.addEventListener('scroll', scrollHandler, { passive: true });
        
        // Store handler for cleanup
        if (!window._scrollHandlers) window._scrollHandlers = [];
        window._scrollHandlers.push(scrollHandler);
    }
    
    return debugMode
        ? { 
            rootId, 
            map: DOM_HASH_MAP, 
            perfMetrics: PERF_METRICS, 
            highlightedElements: getHighlightedElements(),
            interactiveElementsByPosition: indexByPosition ? INTERACTIVE_ELEMENTS_BY_POSITION : undefined
          }
        : { 
            rootId, 
            map: DOM_HASH_MAP, 
            highlightedElements: getHighlightedElements(),
            interactiveElementsByPosition: indexByPosition ? INTERACTIVE_ELEMENTS_BY_POSITION : undefined
          };
} 