"""Excalidraw element factory helpers for building scenes programmatically."""

import random
import time

def rand_id():
    return ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=20))

def rect(x, y, w, h, stroke="#1e1e1e", bg="transparent", fill="hachure", sw=2, roughness=1):
    """Create a rectangle element."""
    return {"id": rand_id(), "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
        "strokeWidth": sw, "roughness": roughness, "opacity": 100, "angle": 0,
        "seed": random.randint(1, 2000000000), "version": 1, "versionNonce": random.randint(1, 2000000000),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "updated": int(time.time()*1000), "link": None, "locked": False}

def ellipse(x, y, w, h, stroke="#1e1e1e", bg="transparent", fill="hachure", sw=2, roughness=1):
    """Create an ellipse element."""
    return {"id": rand_id(), "type": "ellipse", "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
        "strokeWidth": sw, "roughness": roughness, "opacity": 100, "angle": 0,
        "seed": random.randint(1, 2000000000), "version": 1, "versionNonce": random.randint(1, 2000000000),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "updated": int(time.time()*1000), "link": None, "locked": False}

def text(x, y, txt, size=20, color="#1e1e1e", font=2, w=None, align="center"):
    """Create a text element. Font: 1=hand-drawn, 2=normal, 3=code."""
    lines = txt.split('\n')
    h = len(lines) * (size * 1.4)
    width = w or max(len(l) for l in lines) * size * 0.6
    return {"id": rand_id(), "type": "text", "x": x, "y": y, "width": width, "height": h,
        "text": txt, "fontSize": size, "fontFamily": font, "textAlign": align,
        "verticalAlign": "top", "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "hachure", "strokeWidth": 1, "roughness": 1, "opacity": 100, "angle": 0,
        "seed": random.randint(1, 2000000000), "version": 1, "versionNonce": random.randint(1, 2000000000),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "updated": int(time.time()*1000), "link": None, "locked": False}

def arrow(x1, y1, x2, y2, color="#1e1e1e", sw=2, end_head="arrow", start_head=None):
    """Create an arrow element. Points are relative to (x1,y1).
    
    WARNING: This creates a STRAIGHT arrow. For mindmaps/flowcharts,
    use FlowChartCreator.createNodes() via the Chromium bridge instead.
    Manually injected arrows with elbowed:true DO NOT render as elbows.
    See references/flowchart-creator-api.md for the correct approach.
    """
    return {"id": rand_id(), "type": "arrow", "x": x1, "y": y1, "width": x2-x1, "height": y2-y1,
        "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "hachure",
        "strokeWidth": sw, "roughness": 1, "opacity": 100, "angle": 0,
        "seed": random.randint(1, 2000000000), "version": 1, "versionNonce": random.randint(1, 2000000000),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "updated": int(time.time()*1000), "link": None, "locked": False,
        "points": [[0, 0], [x2-x1, y2-y1]],
        "startBinding": None, "endBinding": None,
        "startArrowhead": start_head, "endArrowhead": end_head}

def line(x1, y1, x2, y2, color="#1e1e1e", sw=2):
    """Create a line element (no arrowheads)."""
    return arrow(x1, y1, x2, y2, color=color, sw=sw, end_head=None, start_head=None)

def diamond(x, y, w, h, stroke="#1e1e1e", bg="transparent", fill="hachure", sw=2, roughness=1):
    """Create a diamond element."""
    return {"id": rand_id(), "type": "diamond", "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
        "strokeWidth": sw, "roughness": roughness, "opacity": 100, "angle": 0,
        "seed": random.randint(1, 2000000000), "version": 1, "versionNonce": random.randint(1, 2000000000),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "updated": int(time.time()*1000), "link": None, "locked": False}

# --- Color presets (Mantine palette) ---
COLORS = {
    "dark": "#1e1e1e",
    "gray": "#868e96",
    "red": "#e03131",
    "red-light": "#ffe3e3",
    "pink": "#e64980",
    "grape": "#ae3ec9",
    "violet": "#7048e8",
    "indigo": "#4263eb",
    "blue": "#1971c2",
    "blue-light": "#d0ebff",
    "cyan": "#0c8599",
    "teal": "#0ca678",
    "green": "#2f9e44",
    "green-light": "#ebfbee",
    "lime": "#66a80f",
    "yellow": "#e67700",
    "yellow-light": "#fff9db",
    "orange": "#e8590c",
    "orange-light": "#fff4e6",
    "purple": "#9c36b5",
    "purple-light": "#f3d9fa",
}

# --- Dynamic sizing helpers ---

def text_width(text, font_size):
    """Estimate text width in pixels. Use for dynamic pill sizing."""
    return int(len(text) * font_size * 0.58) + 24

def pill_w(text, font_size, min_w=200):
    """Compute pill width for a given text, respecting minimum."""
    return max(text_width(text, font_size), min_w)

def group_label(x, y, w, h, label, label_w=None, stroke="#868e96", opacity=60):
    """Create a group label: semi-transparent rectangle + label text.
    Use for visual categories (e.g., 'STATIC 28%', 'DYNAMIC 72%').
    """
    gid = 'grp_' + rand_id()[:8]
    lbl_id = 'glbl_' + rand_id()[:8]
    group_rect = rect(x, y, w, h, stroke=stroke, bg="transparent", fill="solid", sw=1, roughness=0)
    group_rect['id'] = gid
    group_rect['opacity'] = opacity
    group_rect['roundness'] = {"type": 3}
    label_text = text(x + 10, y + 6, label, size=14, color=stroke, w=label_w or text_width(label, 14), align="left")
    label_text['id'] = lbl_id
    label_text['opacity'] = opacity + 20
    return [group_rect, label_text]

def elbow_arrow(src_id, tgt_id, color="#1e1e1e", sw=2):
    """Create an elbow arrow between two elements (for post-repositioning injection).
    WARNING: For mindmaps, prefer FlowChartCreator.createNodes() — this is for
    cases where you need to inject arrows AFTER manual repositioning.
    """
    arr = arrow(0, 0, 100, 0, color=color, sw=sw)
    arr['elbowed'] = True
    arr['startBinding'] = {"elementId": src_id, "focus": 0, "gap": 4, "mode": "orbit", "fixedPoint": [1.033, 0.498]}
    arr['endBinding'] = {"elementId": tgt_id, "focus": 0, "gap": 4, "mode": "orbit", "fixedPoint": [-0.033, 0.498]}
    return arr
