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
 * @param {number} args.focusHighlightIndex - If >= 0, only highlight the element with this index.
 * @param {number} args.viewportExpansion - Pixels to expand the viewport bounds for visibility checks. -1 to expand to full page.
 * @param {boolean} args.debugMode - Enables detailed performance metrics and logging.
 *
 * @returns {Object} An object containing the root node ID, a map of all node data, and (if debugMode) performance metrics.
 *
 * @example
 * const result = buildDomTree({ doHighlightElements: true, debugMode: false });
 * // result: { rootId: "0", map: { "0": {...}, ... } }
 */
export default function buildDomTree(args = {
    doHighlightElements: true,
    focusHighlightIndex: -1,
    viewportExpansion: -1,
    debugMode: true,
}) {
    const { doHighlightElements, focusHighlightIndex, viewportExpansion, debugMode } = args;

    // --- Instantiate helpers with shared state ---
    const { PERF_METRICS, measureDomOperation, postProcessMetrics, pushTiming, popTiming } = createMetrics(debugMode);
    const { highlightElement, cleanupHighlights } = createHighlightUtils(pushTiming, popTiming);
    const domUtils = createDomUtils(debugMode, PERF_METRICS, measureDomOperation);

    // --- Main state ---
    let highlightIndex = 0;
    const DOM_HASH_MAP = {};
    const ID = { current: 0 };

    // --- Core Logic ---
    function handleHighlighting(nodeData, node, parentIframe, isParentHighlighted) {
        if (!nodeData.isInteractive) return false;
        // only highlight if parent not highlighted (prevent overlaps) or if its distinct
        let shouldHighlight = !isParentHighlighted || domUtils.isElementDistinctInteraction(node);
        if (shouldHighlight) {
            // only highlight if in viewport (or if its set to -1)
            nodeData.isInViewport = domUtils.isInExpandedViewport(node, viewportExpansion);
            if (nodeData.isInViewport || viewportExpansion === -1) {
                nodeData.highlightIndex = highlightIndex++;
                if (doHighlightElements) {
                    // highlight given node if we aren't focusing on one only
                    if (focusHighlightIndex < 0 || focusHighlightIndex === nodeData.highlightIndex) {
                        const time = highlightElement(node, nodeData.highlightIndex, parentIframe) || 0;
                        if (debugMode) PERF_METRICS.timings.highlightElement += time;
                    }
                    // return true if successful highlight -- this is to signal that children should not be highlighted.
                    return true;
                }
            }
        }
        return false;
    }

    /**
     * Recursively traverses the DOM tree and builds a serializable representation of each node.
     * Handles element filtering, visibility, highlighting, and special cases such as iframes, shadow DOM, and text nodes.
     *
     * @param {Node} node - The current DOM node to process.
     * @param {Element|null} [parentIframe=null] - The parent iframe element if inside an iframe, otherwise null.
     * @param {boolean} [isParentHighlighted=false] - Whether the parent node was highlighted, to avoid redundant highlights.
     * @returns {string|null} The unique ID of the processed node in the DOM_HASH_MAP, or null if the node is skipped.
     *
     * @remarks
     * - Skips nodes that are not elements or text, or are not visible/accepted.
     * - Handles text nodes, shadow DOM, and content-editable regions.
     * - Applies highlighting logic if enabled.
     */
    function buildTreeRecursive(node, parentIframe = null, isParentHighlighted = false) {
        if (debugMode) {
            PERF_METRICS.nodeMetrics.totalNodes++;
            PERF_METRICS.calls.buildDomTree++;
        }
        if (!node || node.id === 'playwright-highlight-container' || (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE)) {
            if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
            return null;
        }
        // process body node
        if (node === document.body) {
            const nodeData = { tagName: 'body', attributes: {}, xpath: '/body', children: [] };
            for (const child of node.childNodes) {
                const domElement = buildTreeRecursive(child, parentIframe, false);
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
            // skip node if no parent node (not interactive) or if part of a script (not interactive in DOM)
            const parentElement = node.parentElement;
            if (!parentElement || parentElement.tagName.toLowerCase() === 'script') {
                if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
                return null;
            }
            const id = `${ID.current++}`;
            DOM_HASH_MAP[id] = { type: "TEXT_NODE", text: textContent, isVisible: domUtils.isTextNodeVisible(node, viewportExpansion) };
            if (debugMode) PERF_METRICS.nodeMetrics.processedNodes++;
            return id;
        }
        // check whether element is of accepted type
        if (!domUtils.isElementAccepted(node)) {
            if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
            return null;
        }

        if (viewportExpansion !== -1) {
            const rect = domUtils.getCachedBoundingRect(node);
            const style = domUtils.getCachedComputedStyle(node);
            // check if element doesnt move when scrolling (fixed or sticky)
            const isFixedOrSticky = style && (style.position === 'fixed' || style.position === 'sticky');
            // skip node if no cached bounding rect or if not in viewport (and not fixed/sticky)
            if (!rect || (!isFixedOrSticky && !domUtils.isInExpandedViewport(node, viewportExpansion))) {
                if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
                return null;
            }
        }

        const nodeData = {
            tagName: node.tagName.toLowerCase(),
            attributes: {},
            xpath: domUtils.getXPathTree(node, true),
            children: [],
            // other potential node data to populate conditionally
            // isInteractive: false,
            // isVisible: false,
            // isTopElement: false,
            // isInViewport: false,
            // highlightIndex: -1,
            // shadowRoot: false,
        };
        // quick check if element is interactive
        if (domUtils.isInteractiveCandidate(node) || nodeData.tagName === 'iframe' || nodeData.tagName === 'body') {
            const attributeNames = node.getAttributeNames?.() || [];
            for (const name of attributeNames) {
                nodeData.attributes[name] = node.getAttribute(name);
            }
        }
        // populate isVisible, isTopElement, isInteractive attributes of nodeData
        let nodeWasHighlighted = false;
        nodeData.isVisible = domUtils.isElementVisible(node);
        if (nodeData.isVisible) {
            nodeData.isTopElement = domUtils.isTopElement(node, viewportExpansion);
            if (nodeData.isTopElement) {
                nodeData.isInteractive = domUtils.isInteractiveElement(node);
                // mark element to be highlighted (so that children are not highlighted)
                nodeWasHighlighted = handleHighlighting(nodeData, node, parentIframe, isParentHighlighted);
            }
        }
        // Check for special types of nodes with internal structures, recurse through those
        const tagName = nodeData.tagName;
        // for iframes
        if (tagName === "iframe") {
            try {
                const iframeDoc = node.contentDocument || node.contentWindow?.document;
                if (iframeDoc) {
                    for (const child of iframeDoc.childNodes) {
                        const domElement = buildTreeRecursive(child, node, false);
                        if (domElement) nodeData.children.push(domElement);
                    }
                }
            } catch (e) { console.warn("Unable to access iframe:", e); }
            // for content editable divs
        } else if (node.isContentEditable || (tagName === "body" && node.getAttribute("data-id")?.startsWith("mce_"))) {
            for (const child of node.childNodes) {
                const domElement = buildTreeRecursive(child, parentIframe, nodeWasHighlighted);
                if (domElement) nodeData.children.push(domElement);
            }

        } else {
            // for shadow DOM elements that have internal structure
            if (node.shadowRoot) {
                nodeData.shadowRoot = true;
                for (const child of node.shadowRoot.childNodes) {
                    const domElement = buildTreeRecursive(child, parentIframe, nodeWasHighlighted);
                    if (domElement) nodeData.children.push(domElement);
                }
            }
            // for all other nodes, recurse through children
            for (const child of node.childNodes) {
                const passHighlightStatusToChild = nodeWasHighlighted || isParentHighlighted;
                const domElement = buildTreeRecursive(child, parentIframe, passHighlightStatusToChild);
                if (domElement) nodeData.children.push(domElement);
            }
        }
        // Skip empty anchor tags only if they have no dimensions and no children
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

    return debugMode
        ? { rootId, map: DOM_HASH_MAP, perfMetrics: PERF_METRICS }
        : { rootId, map: DOM_HASH_MAP };
} 