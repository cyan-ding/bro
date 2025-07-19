// @file purpose: Draws bounding boxes overlay for detected elements on the page.
// This script is injected by Bro to visualize detected elements.

(function(boxes) {
    // Remove old overlay if exists
    let old = document.getElementById('bro-bbox-overlay');
    if (old) old.remove();

    // Create overlay
    let overlay = document.createElement('div');
    overlay.id = 'bro-bbox-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100vw';
    overlay.style.height = '100vh';
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '999999';

    // Draw each box
    for (let i = 0; i < boxes.length; i++) {
        const box = boxes[i];
        let rect = document.createElement('div');
        rect.style.position = 'absolute';
        rect.style.left = box.x + 'px';
        rect.style.top = box.y + 'px';
        rect.style.width = box.width + 'px';
        rect.style.height = box.height + 'px';
        rect.style.border = '2px solid red';
        rect.style.background = 'rgba(255,0,0,0.1)';
        rect.style.boxSizing = 'border-box';
        // Add index label in bottom right
        let label = document.createElement('div');
        label.textContent = i.toString();
        label.style.position = 'absolute';
        label.style.right = '2px';
        label.style.bottom = '2px';
        label.style.background = 'rgba(255,255,255,0.8)';
        label.style.color = 'red';
        label.style.fontSize = '14px';
        label.style.fontWeight = 'bold';
        label.style.padding = '0 2px';
        label.style.pointerEvents = 'none';
        rect.appendChild(label);
        overlay.appendChild(rect);
    }
    document.body.appendChild(overlay);
}) 