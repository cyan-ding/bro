/**
 * @file purpose: Best iframe extraction script that detects all iframe elements including nested ones.
 * This script successfully detects all iframe elements and provides detailed information about them.
 */

/**
 * Simple version that returns just the iframe elements (the most effective approach)
 * @param {Element} root - The root element to start walking from
 * @returns {Array} Array of iframe elements
 */
function findIframes(root = document.body) {
	const iframes = [];
	
	function walk(node) {
		if (!node) return;
		
		if (node.tagName === 'IFRAME') {
			iframes.push({
				element: node,
				tagName: node.tagName,
				className: node.className,
				id: node.id,
				src: node.src,
				name: node.name
			});
		}
		
		// Check regular children
		for (let child of node.children) {
			walk(child);
		}
		
		// Check shadow root children (in case iframes are inside shadow DOM)
		if (node.shadowRoot) {
			for (let child of node.shadowRoot.children) {
				walk(child);
			}
		}
	}
	
	walk(root);
	return iframes;
}

/**
 * Enhanced version that provides detailed information about iframes
 * @param {Element} root - The root element to start walking from
 * @returns {Array} Array of detailed iframe information
 */
function findIframesDetailed(root = document.body) {
	const iframes = [];
	
	function walk(node) {
		if (!node) return;
		
		if (node.tagName === 'IFRAME') {
			// Try to access iframe content (may fail due to CORS)
			let iframeContent = null;
			let iframeDocument = null;
			let iframeBody = null;
			
			try {
				iframeDocument = node.contentDocument;
				if (iframeDocument) {
					iframeBody = iframeDocument.body;
					iframeContent = {
						title: iframeDocument.title,
						url: iframeDocument.URL,
						bodyHTML: iframeBody ? iframeBody.innerHTML : null,
						bodyText: iframeBody ? iframeBody.textContent?.trim() : null
					};
				}
			} catch (e) {
				// CORS error or other access issues
				iframeContent = {
					error: e.message,
					accessible: false
				};
			}
			
			iframes.push({
				tagName: node.tagName,
				className: node.className,
				id: node.id,
				name: node.name,
				src: node.src,
				width: node.width,
				height: node.height,
				allow: node.allow,
				allowfullscreen: node.allowfullscreen,
				loading: node.loading,
				sandbox: node.sandbox,
				scrolling: node.scrolling,
				seamless: node.seamless,
				attributes: Array.from(node.attributes).map(attr => ({
					name: attr.name,
					value: attr.value
				})),
				iframeContent: iframeContent,
				computedStyle: {
					width: getComputedStyle(node).width,
					height: getComputedStyle(node).height,
					display: getComputedStyle(node).display,
					visibility: getComputedStyle(node).visibility,
					position: getComputedStyle(node).position
				}
			});
		}
		
		// Check regular children
		for (let child of node.children) {
			walk(child);
		}
		
		// Check shadow root children (in case iframes are inside shadow DOM)
		if (node.shadowRoot) {
			for (let child of node.shadowRoot.children) {
				walk(child);
			}
		}
	}
	
	walk(root);
	return iframes;
}

/**
 * Extracts iframe information using the most effective approach and returns a summary
 * @param {Element} root - The root element to start walking from
 * @returns {Object} Summary of iframe extraction
 */
function extractIframesBestSummary(root = document.body) {
	const iframeElements = findIframesDetailed(root);
	
	return {
		totalIframes: iframeElements.length,
		iframeElements: iframeElements,
		summary: iframeElements.map(iframe => ({
			hostTag: iframe.tagName,
			hostClass: iframe.className,
			hostId: iframe.id,
			hostName: iframe.name,
			src: iframe.src,
			width: iframe.width,
			height: iframe.height,
			accessible: iframe.iframeContent && !iframe.iframeContent.error,
			hasContent: iframe.iframeContent && iframe.iframeContent.bodyHTML,
			contentLength: iframe.iframeContent && iframe.iframeContent.bodyHTML ? iframe.iframeContent.bodyHTML.length : 0
		}))
	};
}

/**
 * Attempts to extract content from all accessible iframes
 * @param {Element} root - The root element to start walking from
 * @returns {Object} Object containing iframe content extraction results
 */
function extractIframeContent(root = document.body) {
	const iframeElements = findIframesDetailed(root);
	const contentResults = [];
	
	iframeElements.forEach((iframe, index) => {
		const result = {
			index: index,
			tagName: iframe.tagName,
			id: iframe.id,
			name: iframe.name,
			src: iframe.src,
			accessible: false,
			content: null,
			error: null
		};
		
		if (iframe.iframeContent && !iframe.iframeContent.error) {
			result.accessible = true;
			result.content = iframe.iframeContent;
		} else if (iframe.iframeContent && iframe.iframeContent.error) {
			result.error = iframe.iframeContent.error;
		} else {
			result.error = "Unable to access iframe content";
		}
		
		contentResults.push(result);
	});
	
	return {
		totalIframes: iframeElements.length,
		accessibleIframes: contentResults.filter(r => r.accessible).length,
		contentResults: contentResults
	};
}

// Expose functions to window object for external access
window.findIframes = findIframes;
window.findIframesDetailed = findIframesDetailed;
window.extractIframesBestSummary = extractIframesBestSummary;
window.extractIframeContent = extractIframeContent; 