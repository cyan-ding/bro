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
 * Args:
 *   args (Object): Configuration options for the DOM tree builder.
 *     - doHighlightElements (boolean): Whether to visually highlight interactive elements.
 *     - focusHighlightIndex (number): If >= 0, only highlight the element with this index.
 *     - viewportExpansion (number): Pixels to expand the viewport bounds for visibility checks. -1 to expand to full page
 *     - debugMode (boolean): Enables detailed performance metrics and logging.
 *
 * Returns:
 *   Object: An object containing the root node ID, a map of all node data, and (if debugMode) performance metrics.
 *
 * Examples:
 *   const result = buildDomTree({ doHighlightElements: true, debugMode: false });
 *   // result: { rootId: "0", map: { "0": {...}, ... } }
 */

export default function buildDomTree(args = {
    doHighlightElements: true,
    focusHighlightIndex: -1,
    viewportExpansion: -1,
    debugMode: true,
}) {
    const { doHighlightElements, focusHighlightIndex, viewportExpansion, debugMode } = args;

    // --- Instantiate helpers with shared state ---
    const { PERF_METRICS, measureTime, measureDomOperation, postProcessMetrics, pushTiming, popTiming } = createMetrics(debugMode);
    const { highlightElement, cleanupHighlights } = createHighlightUtils(pushTiming, popTiming);
    const domUtils = createDomUtils(debugMode, PERF_METRICS, measureDomOperation);

    // --- Main state ---
    let highlightIndex = 0;
    const DOM_HASH_MAP = {};
    const ID = { current: 0 };

    // --- Core Logic ---
    function handleHighlighting(nodeData, node, parentIframe, isParentHighlighted) {
        if (!nodeData.isInteractive) return false;
        let shouldHighlight = !isParentHighlighted || domUtils.isElementDistinctInteraction(node);
        if (shouldHighlight) {
            nodeData.isInViewport = domUtils.isInExpandedViewport(node, viewportExpansion);
            if (nodeData.isInViewport || viewportExpansion === -1) {
                nodeData.highlightIndex = highlightIndex++;
                if (doHighlightElements) {
                    if (focusHighlightIndex < 0 || focusHighlightIndex === nodeData.highlightIndex) {
                        highlightElement(node, nodeData.highlightIndex, parentIframe);
                    }
                    return true;
                }
            }
        }
        return false;
    }

    // Use a renamed inner function to avoid confusion with the outer export
    // Main function to recursively traverse DOM tree. 
    function buildTreeRecursive(node, parentIframe = null, isParentHighlighted = false) {
        if (debugMode) PERF_METRICS.nodeMetrics.totalNodes++;
        if (!node || node.id === 'playwright-highlight-container' || (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE)) {
            if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
            return null;
        }

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

        if (node.nodeType === Node.TEXT_NODE) {
            const textContent = node.textContent.trim();
            if (!textContent) {
                if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
                return null;
            }
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

        if (!domUtils.isElementAccepted(node)) {
            if (debugMode) PERF_METRICS.nodeMetrics.skippedNodes++;
            return null;
        }

        if (viewportExpansion !== -1) {
            const rect = domUtils.getCachedBoundingRect(node);
            const style = domUtils.getCachedComputedStyle(node);
            const isFixedOrSticky = style && (style.position === 'fixed' || style.position === 'sticky');
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
        };

        if (domUtils.isInteractiveCandidate(node) || nodeData.tagName === 'iframe' || nodeData.tagName === 'body') {
            const attributeNames = node.getAttributeNames?.() || [];
            for (const name of attributeNames) {
                nodeData.attributes[name] = node.getAttribute(name);
            }
        }

        let nodeWasHighlighted = false;
        nodeData.isVisible = domUtils.isElementVisible(node);
        if (nodeData.isVisible) {
            nodeData.isTopElement = domUtils.isTopElement(node, viewportExpansion);
            if (nodeData.isTopElement) {
                nodeData.isInteractive = domUtils.isInteractiveElement(node);
                nodeWasHighlighted = handleHighlighting(nodeData, node, parentIframe, isParentHighlighted);
            }
        }
        // Check for special types of nodes
        const tagName = nodeData.tagName;
        // iframe
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
            // for shadow DOM elements
        } else {
            if (node.shadowRoot) {
                nodeData.shadowRoot = true;
                for (const child of node.shadowRoot.childNodes) {
                    const domElement = buildTreeRecursive(child, parentIframe, nodeWasHighlighted);
                    if (domElement) nodeData.children.push(domElement);
                }
            }
            for (const child of node.childNodes) {
                const passHighlightStatusToChild = nodeWasHighlighted || isParentHighlighted;
                const domElement = buildTreeRecursive(child, parentIframe, passHighlightStatusToChild);
                if (domElement) nodeData.children.push(domElement);
            }
        }

        if (tagName === 'a' && nodeData.children.length === 0 && !nodeData.attributes.href) {
            const rect = domUtils.getCachedBoundingRect(node);
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

    const wrappedBuildTree = measureTime(buildTreeRecursive, 'buildDomTree');
    const rootId = wrappedBuildTree(document.body);

    if (debugMode) {
        postProcessMetrics();
    }

    return debugMode
        ? { rootId, map: DOM_HASH_MAP, perfMetrics: PERF_METRICS }
        : { rootId, map: DOM_HASH_MAP };
} 