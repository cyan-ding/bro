// Single-pass viewport observer for the fast loop: interactive elements, visible text and scroll state.
// Element handles are kept in window.__broEls so Python can act on them without selectors.
(args) => {
  const { maxTextChars, maxElements } = args;
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "PATH", "HEAD", "META", "LINK"]);
  const TAGS = new Set(["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA", "SUMMARY", "OPTION", "LABEL"]);
  const ROLES = new Set([
    "button", "link", "checkbox", "radio", "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "option",
    "combobox", "textbox", "searchbox", "switch", "slider", "spinbutton", "listbox", "treeitem",
  ]);
  const CHROME_TAGS = new Set(["NAV", "HEADER", "FOOTER", "ASIDE"]);
  const CHROME_ROLES = new Set(["navigation", "banner", "contentinfo", "menu", "menubar", "toolbar"]);
  const ATTRS = ["type", "placeholder", "aria-label", "role", "name", "alt", "title", "aria-expanded", "href"];
  const mainEl = document.querySelector("main, [role=main]");
  const elements = [];
  const handles = [];
  const textParts = [];
  let textLen = 0;

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

  function attrsOf(el) {
    const out = {};
    for (const key of ATTRS) {
      const val = el.getAttribute(key);
      if (val) out[key] = val.length > 120 ? val.slice(0, 120) : val;
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      if (el.type !== "password" && el.value) out.value = el.value.slice(0, 60);
      if (el.type === "checkbox" || el.type === "radio") out.checked = String(el.checked);
    } else if (el.tagName === "SELECT" && el.selectedOptions.length) {
      out.value = clean(el.selectedOptions[0].textContent).slice(0, 60);
    }
    return out;
  }

  function isReal(el) {
    if (TAGS.has(el.tagName)) return true;
    const role = (el.getAttribute("role") || "").toLowerCase();
    return ROLES.has(role) || el.isContentEditable;
  }

  function isClickable(el, cs) {
    return el.hasAttribute("onclick") || (el.tabIndex >= 0 && el.tagName !== "BODY") || cs.cursor === "pointer";
  }

  function addText(t, inline) {
    if (t.length < 2 || textLen >= maxTextChars) return;
    if (inline && textParts.length > 0) textParts[textParts.length - 1] += " " + t;
    else textParts.push(t);
    textLen += t.length + 3;
  }

  // Visits text nodes and child elements in document order so sentences stay intact.
  function walk(root, offsetX, offsetY, realAncestor, textOk, inline) {
    for (const node of root.childNodes) {
      if (node.nodeType === 3) {
        if (textOk) addText(clean(node.textContent), inline);
        continue;
      }
      if (node.nodeType !== 1) continue;
      const el = node;
      const tag = el.tagName.toUpperCase();
      if (SKIP.has(tag) || el.hasAttribute("data-bro-overlay")) continue;
      const rect = el.getBoundingClientRect();
      const top = rect.top + offsetY, bottom = rect.bottom + offsetY;
      const left = rect.left + offsetX, right = rect.right + offsetX;
      const hasSize = rect.width > 0 && rect.height > 0;
      if (hasSize && (bottom < 0 || top > vh || right < 0 || left > vw)) continue;
      const cs = window.getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      let ancestor = realAncestor;
      if (hasSize && cs.opacity !== "0" && elements.length < maxElements) {
        const real = isReal(el);
        if (real || (!realAncestor && isClickable(el, cs))) {
          const text = clean(tag === "SELECT" ? "" : el.innerText).slice(0, 80);
          const attrs = attrsOf(el);
          if (real || text || attrs["aria-label"] || attrs.alt) {
            elements.push({ index: elements.length, tag: tag.toLowerCase(), attrs, text });
            handles.push(el);
          }
          if (real) ancestor = el;
        }
      }
      const elInline = cs.display.startsWith("inline");
      const isChrome = CHROME_TAGS.has(tag) || CHROME_ROLES.has((el.getAttribute("role") || "").toLowerCase());
      const childTextOk = hasSize && !isChrome && (textOk || el === mainEl);
      if (hasSize && tag === "IMG" && el.alt) addText(clean(el.alt), elInline);
      if (tag === "IFRAME") {
        try {
          const doc = el.contentDocument;
          if (doc && doc.body) walk(doc.body, left, top, ancestor, true, false);
        } catch (e) {
          /* cross-origin */
        }
        continue;
      }
      if (el.shadowRoot) walk(el.shadowRoot, offsetX, offsetY, ancestor, childTextOk, elInline);
      walk(el, offsetX, offsetY, ancestor, childTextOk, elInline);
    }
  }

  walk(document.body, 0, 0, null, mainEl === null, false);
  window.__broEls = handles;
  return {
    url: location.href,
    title: document.title,
    elements,
    text: textParts.join(" | ").slice(0, maxTextChars),
    scroll: {
      y: Math.round(window.scrollY),
      h: Math.round(vh),
      total: Math.round(document.documentElement.scrollHeight),
    },
  };
}
