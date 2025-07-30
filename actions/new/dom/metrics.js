/**
 * @fileoverview
 * This file provides a factory function `createMetrics` that returns a suite of performance and timing
 * utility functions. These helpers are used for measuring execution time and collecting performance
 * metrics, but only when `debugMode` is enabled.
 *
 * The factory pattern allows these stateful operations to be cleanly encapsulated and controlled by a
 * single `debugMode` flag, without polluting the global scope.
 */

export function createMetrics(debugMode) {
    /**
     * A stack for tracking the duration of nested function calls.
     */
    const TIMING_STACK = {
        nodeProcessing: [],
        treeTraversal: [],
        highlighting: [],
        current: null
    };

    /**
     * Pushes a timestamp onto the timing stack for a given operation type.
     * Only active in debug mode. Only used in @highlightElement
     */
    function pushTiming(type) {
        if (!debugMode) return;
        TIMING_STACK[type] = TIMING_STACK[type] || [];
        TIMING_STACK[type].push(performance.now());
    }

    /**
     * Pops a timestamp from the timing stack and returns the elapsed duration.
     * Only active in debug mode. Only used in @highlightElement
     */
    function popTiming(type) {
        if (!debugMode) return 0;
        const start = TIMING_STACK[type].pop();
        return performance.now() - start;
    }

    /**
     * A container for all performance metrics collected during execution.
     * Initialized only in debug mode.
     */
    const PERF_METRICS = debugMode ? {
        calls: {
            buildDomTree: 0, highlightElement: 0, isElementVisible: 0,
            isTopElement: 0, isInExpandedViewport: 0, isTextNodeVisible: 0, getEffectiveScroll: 0,
            getCachedBoundingRect: 0, getCachedComputedStyle: 0, getCachedClientRects: 0, getXPathTree: 0,
            isInteractiveElement: 0, isElementAccepted: 0, isElementDistinctInteraction: 0, isInteractiveCandidate: 0,
        },
        timings: {
            buildDomTree: 0, highlightElement: 0, isElementVisible: 0,
            isTopElement: 0, isInExpandedViewport: 0, isTextNodeVisible: 0, getEffectiveScroll: 0,
            getCachedBoundingRect: 0, getCachedComputedStyle: 0, getCachedClientRects: 0, getXPathTree: 0,
            isInteractiveElement: 0, isElementAccepted: 0, isElementDistinctInteraction: 0, isInteractiveCandidate: 0,
        },
        cacheMetrics: {
            boundingRectCacheHits: 0, boundingRectCacheMisses: 0, computedStyleCacheHits: 0, 
            computedStyleCacheMisses: 0, clientRectsCacheHits: 0, clientRectsCacheMisses: 0, 
            boundingRectHitRate: 0, computedStyleHitRate: 0, overallHitRate: 0
        },
        nodeMetrics: { totalNodes: 0, processedNodes: 0, skippedNodes: 0 },
    } : null;

    /**
     * Measures the execution time of a specific DOM operation (e.g., getBoundingClientRect).
     * Records the duration and count in `PERF_METRICS`. Only active in debug mode.
     */
    function measureDomOperation(operation, name) {
        if (!debugMode) return operation;
        return function (...args) {
            const start = performance.now();
            const result = operation.apply(this, args);
            const duration = performance.now() - start;
            if (PERF_METRICS && name in PERF_METRICS.calls) {
                PERF_METRICS.calls[name]++;
                PERF_METRICS.timings[name] += duration;
            }
            return result;
        }
    }

    /**
     * Calculates final derived metrics (e.g., hit rates, averages) after the main execution is complete.
     * Only active in debug mode.
     */
    function postProcessMetrics() {
        if (!debugMode || !PERF_METRICS) return;
        // convert to seconds
        Object.keys(PERF_METRICS.timings).forEach(key => { PERF_METRICS.timings[key] /= 1000; });
        // calculate style and bounding rect hit rates
        const boundingRectTotal = PERF_METRICS.cacheMetrics.boundingRectCacheHits + PERF_METRICS.cacheMetrics.boundingRectCacheMisses;
        const computedStyleTotal = PERF_METRICS.cacheMetrics.computedStyleCacheHits + PERF_METRICS.cacheMetrics.computedStyleCacheMisses;
        if (boundingRectTotal > 0) PERF_METRICS.cacheMetrics.boundingRectHitRate = PERF_METRICS.cacheMetrics.boundingRectCacheHits / boundingRectTotal;
        if (computedStyleTotal > 0) PERF_METRICS.cacheMetrics.computedStyleHitRate = PERF_METRICS.cacheMetrics.computedStyleCacheHits / computedStyleTotal;
        if ((boundingRectTotal + computedStyleTotal) > 0) PERF_METRICS.cacheMetrics.overallHitRate = (PERF_METRICS.cacheMetrics.boundingRectCacheHits + PERF_METRICS.cacheMetrics.computedStyleCacheHits) / (boundingRectTotal + computedStyleTotal);
    }

    return {
        pushTiming,
        popTiming,
        PERF_METRICS,
        measureDomOperation,
        postProcessMetrics
    };
} 