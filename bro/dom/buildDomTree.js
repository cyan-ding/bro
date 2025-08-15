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
    debugMode: false,
    overlapThreshold: 0.7, // Threshold for area overlap detection (0.7 = 70%)
    indexByPosition: true, // Whether to index interactive elements by position
}) {
    // mark that dom tree has been injnected
    window.domTreeInjected = true;
    
    const { doHighlightElements, debugMode, overlapThreshold, indexByPosition } = args;

    // --- Instantiate helpers with shared state ---
    const { PERF_METRICS, measureDomOperation, postProcessMetrics, pushTiming, popTiming } = createMetrics(debugMode);
    const domUtils = createDomUtils(debugMode, PERF_METRICS, measureDomOperation);
    const { highlightElement, cleanupHighlights, getHighlightedElements, createScrollHandler } = 
        createHighlightUtils(pushTiming, popTiming, domUtils.getXPathTree);

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
    function buildTreeRecursive(node, parentIframe = null, highlightedAncestor = null, isInViewport = false, highlightDepth = 0) {
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
                const domElement = buildTreeRecursive(child, parentIframe, highlightedAncestor, isInViewport, highlightDepth);
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

        // Compute isInteractive only once if needed, and avoid redundant domUtils.isInteractiveElement calls
        
        if (nodeData.isVisible) {
            nodeData.isInteractive = domUtils.isInteractiveElement(node);
            // mark element to be highlighted (so that children are not highlighted)
            if (domUtils.isSufficientlyVisibleInViewport(node)) {
                newHighlightedAncestor = handleHighlighting(nodeData, node, parentIframe, highlightedAncestor);
                if (nodeData.highlightIndex !== undefined) {
                    nodeData.highlightDepth = highlightDepth;
                }
            }
            if (indexByPosition) {
                domUtils.indexElementByPosition(node, nodeData, INTERACTIVE_ELEMENTS_BY_POSITION, POSITION_GRID_SIZE);
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
                        const nextDepth = nodeData.highlightIndex !== undefined ? highlightDepth + 1 : highlightDepth;
                        const domElement = buildTreeRecursive(child, node, newHighlightedAncestor, false, nextDepth);
                        if (domElement) nodeData.children.push(domElement);
                    }
                }
            } catch (e) { console.warn("Unable to access iframe:", e); }
        } else if (node.shadowRoot) {
            // for shadow DOM elements that have internal structure
            nodeData.shadowRoot = true;
            for (const child of node.shadowRoot.childNodes) {
                const nextDepth = nodeData.highlightIndex !== undefined ? highlightDepth + 1 : highlightDepth;
                const domElement = buildTreeRecursive(child, parentIframe, newHighlightedAncestor, false, nextDepth);
                if (domElement) nodeData.children.push(domElement);
            }
            for (const child of node.childNodes) {
                const nextDepth = nodeData.highlightIndex !== undefined ? highlightDepth + 1 : highlightDepth;
                const domElement = buildTreeRecursive(child, parentIframe, newHighlightedAncestor, false, nextDepth);
                if (domElement) nodeData.children.push(domElement);
            }
        } else {
            // for all other nodes, recurse through children
            for (const child of node.childNodes) {
                const nextDepth = nodeData.highlightIndex !== undefined ? highlightDepth + 1 : highlightDepth;
                const domElement = buildTreeRecursive(child, parentIframe, newHighlightedAncestor, false, nextDepth);
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
    if (window._scrollHandler) { 
        // remove scroll handler after every buildDomTree call; this happens by default on opening new pages, but needs to be done manually for SPAs
        window.removeEventListener('scroll', window._scrollHandler, true);
        window._scrollHandler = null;
    }

    const wrappedBuildTree = measureDomOperation(buildTreeRecursive, 'buildDomTree');
    if (debugMode) PERF_METRICS.calls.buildDomTree--; // remove this extra call to measureDomOperation
    const rootId = wrappedBuildTree(document.body);

    postProcessMetrics();
    
    // --- Post-processing: conservative attributes, text, newness, and serialization ---
    function capText(value, maxLen = 15) {
        if (value == null) return '';
        const s = String(value);
        return s.length <= maxLen ? s : s.slice(0, maxLen);
    }

    function normalizeWhitespace(str) {
        if (!str) return '';
        return String(str).replace(/\s+/g, ' ').trim();
    }

    function collectTextFor(nodeId, highlightedIdSet, selfId) {
        const node = DOM_HASH_MAP[nodeId];
        if (!node) return '';
        if (node.highlightIndex != null && nodeId !== selfId) return '';
        if (node.type === 'TEXT_NODE') {
            return node.isVisible ? node.text : '';
        }
        let out = '';
        const kids = node.children || [];
        for (const childId of kids) {
            if (highlightedIdSet.has(childId) && childId !== selfId) continue;
            const part = collectTextFor(childId, highlightedIdSet, selfId);
            if (part) out += (out ? ' ' : '') + part;
        }
        return normalizeWhitespace(out);
    }

    function pruneAttributes(tagName, attrs, elementText) {
        const allowed = [
            'title', 'type', 'checked', 'name', 'role', 'value', 'placeholder',
            'data-date-format', 'alt', 'aria-label', 'aria-expanded', 'data-state',
            'aria-checked', 'href', 'src'
        ];
        const out = {};
        const seenByValue = new Map();
        const textLower = (elementText || '').trim().toLowerCase();
        for (const key of allowed) {
            if (!attrs || !Object.prototype.hasOwnProperty.call(attrs, key)) continue;
            let val = attrs[key];
            if (val == null || val === '') continue;

            if (key === 'value' && (attrs['type'] || '').toLowerCase() === 'password') {
                continue;
            }
            if (key === 'role' && String(val).toLowerCase() === String(tagName).toLowerCase()) {
                continue;
            }
            if ((key === 'aria-label' || key === 'placeholder' || key === 'title') && textLower) {
                if (String(val).trim().toLowerCase() === textLower) continue;
            }
            const valStr = String(val);
            if (valStr.length > 5) {
                if (seenByValue.has(valStr)) continue;
                seenByValue.set(valStr, key);
            }
            out[key] = capText(valStr, 15);
        }
        return out;
    }

    function buildIdentityKey(tagName, xpath, attrs) {
        const stableKeys = ['name', 'type', 'aria-label', 'title', 'placeholder'];
        const parts = [String(tagName || ''), String(xpath || '')];
        for (const k of stableKeys) {
            if (attrs && Object.prototype.hasOwnProperty.call(attrs, k)) {
                parts.push(`${k}=${attrs[k]}`);
            }
        }
        return parts.join('|');
    }

    function serializeHighlightedElements() {
        const items = [];
        const highlightedIds = Object.keys(DOM_HASH_MAP).filter(id => {
            const n = DOM_HASH_MAP[id];
            return n && n.highlightIndex != null;
        });
        const highlightedIdSet = new Set(highlightedIds);
        const seen = (window._highlightSeen = window._highlightSeen || new Set());

        // Build a fallback map of raw textContent by highlight index from the visual highlighter
        const rawHighlighted = getHighlightedElements();
        const rawTextByIndex = new Map();
        for (const el of rawHighlighted || []) {
            try {
                const idx = el && typeof el.index === 'number' ? el.index : undefined;
                if (idx !== undefined) {
                    const t = el.info && el.info.textContent ? normalizeWhitespace(el.info.textContent) : '';
                    if (t) rawTextByIndex.set(idx, t);
                }
            } catch (_) { /* no-op */ }
        }

        const nodes = highlightedIds
            .map(id => ({ id, node: DOM_HASH_MAP[id] }))
            .sort((a, b) => (a.node.highlightIndex || 0) - (b.node.highlightIndex || 0));

        for (const { id, node } of nodes) {
            const tag = node.tagName || 'unknown';
            const xpath = node.xpath || '';
            const depth = node.highlightDepth || 0;
            const index = node.highlightIndex;
            const textRaw = collectTextFor(id, highlightedIdSet, id);
            let text = capText(textRaw, 100);
            // Fallback to raw highlight's element.textContent if tree-derived text is empty
            if (!text) {
                const fallback = rawTextByIndex.get(index) || '';
                if (fallback) text = capText(fallback, 100);
            }
            const attrs = pruneAttributes(tag, node.attributes || {}, textRaw);
            const identityKey = buildIdentityKey(tag, xpath, attrs);
            const isNew = !seen.has(identityKey);
            seen.add(identityKey);

            const info = {
                placeholder: attrs['placeholder'],
                role: attrs['role'],
                ariaLabel: attrs['aria-label'],
                type: attrs['type'],
                textContent: text
            };
            const hrefTop = attrs['href'] || undefined;

            items.push({ index, tag, xpath, attrs, text, isNew, depth, href: hrefTop, info });
        }
        return items;
    }
    
    // Set up scroll handler if position indexing is enabled
    if (indexByPosition) {
        const scrollHandler = createScrollHandler(INTERACTIVE_ELEMENTS_BY_POSITION, POSITION_GRID_SIZE);
        window.addEventListener('scroll', scrollHandler, true);
        window._scrollHandler = scrollHandler;
    }
    
    return {
    	rootId,
    	map: DOM_HASH_MAP,
    	...(debugMode ? { perfMetrics: PERF_METRICS } : {}),
	    highlightedElements: getHighlightedElements(),
	    highlightedElementsSerialized: serializeHighlightedElements(),
    	interactiveElementsByPosition: indexByPosition ? INTERACTIVE_ELEMENTS_BY_POSITION : undefined
    };
} 