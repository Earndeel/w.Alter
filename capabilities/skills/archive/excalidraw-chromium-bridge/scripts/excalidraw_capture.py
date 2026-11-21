#!/usr/bin/env python3
"""
Excalidraw canvas capture — extracts the rendered canvas as PNG.
Solves the headless Chromium font rendering issue where page.screenshot()
shows blank text but canvas.toDataURL() captures everything correctly.

Usage:
    python3 excalidraw_capture.py <room_url> [--output diagram.png] [--width 3840] [--height 2160]
    python3 excalidraw_capture.py https://excalidraw.com/#room=abc,key -o /tmp/diagram.png
"""

from playwright.sync_api import sync_playwright
import base64
import argparse
import sys

ROOM_URL_DEFAULT = "https://excalidraw.com/#room=658703d9161ac2d460b3,mpuQZsj1ZApHGH-8ohGJHg"

JS_FIND_STORE = """
var root = document.getElementById('root');
var key = Object.getOwnPropertyNames(root).find(function(k){ return k.indexOf('__reactContainer') === 0; });
var fiber = root[key]; var store = null;
function findStore(n, d) {
    if(!n || d > 60 || store) return;
    var hs = n.memoizedState; var hi = 0;
    while(hs && hi < 30) {
        var ms = hs.memoizedState;
        if(ms && typeof ms === 'object' && ms !== null && typeof ms.updateScene === 'function') { store = ms; return; }
        hs = hs.next; hi++;
    }
    findStore(n.child, d+1); findStore(n.sibling, d+1);
}
findStore(fiber.child, 0);
"""

def capture_excalidraw(room_url, output_path, width=3840, height=2160, wait_ms=15000, filter_bounds=None):
    """Capture Excalidraw canvas as PNG.
    
    Args:
        room_url: Full room URL with key
        output_path: Where to save the PNG
        width: Viewport width (3840 = 4K recommended for readable labels)
        height: Viewport height (2160 = 4K)
        wait_ms: Wait time for collab sync and font loading
        filter_bounds: Optional dict {x_min, y_min, x_max, y_max} to scroll to specific area
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": width, "height": height})
        page.goto(room_url, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
        
        # Optionally scroll to a specific area
        if filter_bounds:
            bounds = filter_bounds
            scroll_js = JS_FIND_STORE + """
            var els = store.getSceneElements().filter(function(e) {
                return !e.isDeleted && 
                    e.x >= """ + str(bounds.get('x_min', 0)) + """ && 
                    e.y >= """ + str(bounds.get('y_min', 0)) + """ &&
                    e.y <= """ + str(bounds.get('y_max', 99999)) + """;
            });
            if(els.length > 0) store.scrollToContent(els, {fitToContent: true});
            """
            page.evaluate(scroll_js)
            page.wait_for_timeout(2000)
        else:
            # Scroll to all content
            page.evaluate(JS_FIND_STORE + "store.scrollToContent(store.getSceneElements(), {fitToContent: true});")
            page.wait_for_timeout(2000)
        
        # Force a re-render (mouse move triggers canvas repaint)
        page.mouse.move(width // 2, height // 2)
        page.mouse.down()
        page.mouse.move(width // 2 + 1, height // 2 + 1)
        page.mouse.up()
        page.wait_for_timeout(1000)
        
        # Extract static canvas (index 0)
        canvas_b64 = page.evaluate("""(function(){
            var canvases = document.querySelectorAll('canvas');
            return canvases[0].toDataURL('image/png');
        })()""")
        
        b64_data = canvas_b64.split(',')[1]
        with open(output_path, 'wb') as f:
            f.write(base64.b64decode(b64_data))
        
        # Also get element count for verification
        count = page.evaluate("(" + JS_FIND_STORE + "return store.getSceneElements().filter(function(e){return !e.isDeleted;}).length;)")
        
        browser.close()
        return {"elements": count, "output": output_path, "size_kb": len(b64_data) * 3 // 4 // 1024}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture Excalidraw canvas as PNG")
    parser.add_argument("room_url", nargs="?", default=ROOM_URL_DEFAULT, help="Full room URL with key")
    parser.add_argument("-o", "--output", default="/tmp/excalidraw_capture.png", help="Output PNG path")
    parser.add_argument("--width", type=int, default=3840, help="Viewport width")
    parser.add_argument("--height", type=int, default=2160, help="Viewport height")
    parser.add_argument("--wait", type=int, default=15000, help="Wait time in ms")
    args = parser.parse_args()
    
    result = capture_excalidraw(args.room_url, args.output, args.width, args.height, args.wait)
    print(f"Captured {result['elements']} elements → {result['output']} ({result['size_kb']}KB)")
