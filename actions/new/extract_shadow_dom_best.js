/**
 * @file purpose: Best shadow DOM extraction script based on the findShadowHosts approach.
 * This script successfully detects all shadow DOM elements including nested ones.
 */


/**
 * Simple version that returns just the host elements with shadow roots (the most effective approach)
 * @param {Element} root - The root element to start walking from
 * @returns {Array} Array of elements that have shadow roots
 */
function findShadowHosts(root = document.body) {
	const hosts = [];
	
	function walk(node) {
		if (!node) return;
		
		if (node.shadowRoot) {
			hosts.push({
				element: node,
				tagName: node.tagName,
				className: node.className,
				id: node.id
			});
		}
		
		// Check regular children
		for (let child of node.children) {
			walk(child);
		}
		
		// Check shadow root children (this is crucial for finding nested shadow DOM)
		if (node.shadowRoot) {
			for (let child of node.shadowRoot.children) {
				walk(child);
			}
		}
	}
	
	walk(root);
	return hosts;
}

/**
 * Enhanced version that provides detailed information about shadow hosts
 * @param {Element} root - The root element to start walking from
 * @returns {Array} Array of detailed shadow host information
 */
function findShadowHostsDetailed(root = document.body) {
	const hosts = [];
	
	function walk(node) {
		if (!node) return;
		
		if (node.shadowRoot) {
			hosts.push({
				tagName: node.tagName,
				className: node.className,
				id: node.id,
				attributes: Array.from(node.attributes).map(attr => ({
					name: attr.name,
					value: attr.value
				})),
				shadowRoot: {
					mode: node.shadowRoot.mode,
					delegatesFocus: node.shadowRoot.delegatesFocus,
					innerHTML: node.shadowRoot.innerHTML,
					textContent: node.shadowRoot.textContent?.trim()
				}
			});
		}
		
		// Check regular children
		for (let child of node.children) {
			walk(child);
		}
		
		// Check shadow root children (this is crucial for finding nested shadow DOM)
		if (node.shadowRoot) {
			for (let child of node.shadowRoot.children) {
				walk(child);
			}
		}
	}
	
	walk(root);
	return hosts;
}

/**
 * Extracts shadow DOM using the most effective approach and returns a summary
 * @param {Element} root - The root element to start walking from
 * @returns {Object} Summary of shadow DOM extraction
 */
function extractShadowDOMBestSummary(root = document.body) {
	const shadowElements = findShadowHostsDetailed(root);
	
	return {
		totalShadowRoots: shadowElements.length,
		shadowElements: shadowElements,
		summary: shadowElements.map(shadow => ({
			hostTag: shadow.tagName,
			hostClass: shadow.className,
			hostId: shadow.id,
			shadowMode: shadow.shadowRoot.mode,
			shadowChildrenCount: shadow.shadowRoot.innerHTML ? shadow.shadowRoot.innerHTML.split('<').length - 1 : 0
		}))
	};
}

// Expose functions to window object for external access
window.findShadowHosts = findShadowHosts;
window.findShadowHostsDetailed = findShadowHostsDetailed;
window.extractShadowDOMBestSummary = extractShadowDOMBestSummary; 