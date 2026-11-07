#!/usr/bin/env python3
"""Generate a horizontal mindmap in tldraw with 3-segment elbow arrows.

Connects from VPS via SSH tunnel to Mac running tldraw offline.
Requires: tldraw offline open on Mac, Agent Skills installed, token stored at
/tmp/tldraw_token.txt on the Mac.

Usage:
    python3 elbow-mindmap.py

Produces a left-to-right mindmap with:
  - 1 root node (blue)
  - 7 L1 branches (black, stacked vertically)
  - 5 L2 leaves per branch (grey)
  - 3-segment elbow arrows (horizontal → vertical → horizontal) at every connection
"""

import json, urllib.request, subprocess, sys

BASE = "http://localhost:7236"
MAC_USER = "lucasjouvencon"
MAC_IP = "100.127.150.1"  # Tailscale IP

def get_token():
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
         f"{MAC_USER}@{MAC_IP}", "cat", "/tmp/tldraw_token.txt"],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()

def req(endpoint, data, token):
    body = json.dumps(data).encode()
    r = urllib.request.Request(f"{BASE}/{endpoint}", body, {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    return json.loads(urllib.request.urlopen(r, timeout=15).read())

# ── Diagram data (customize per use case) ─────────────────────────────
BRANCHES = [
    ("HERMES CORE", ["Agent Loop", "Skills (284)", "Profiles", "Memory Stack", "Tools Registry"]),
    ("PROVIDERS", ["OpenRouter", "Kie.ai", "Anthropic", "Gemini AI", "MiMo", "Codex"]),
    ("INFRASTRUCTURE", ["VPS Oracle ARM", "MacBook Pro", "Tailscale", "SSH Tunnels", "Cloudflare"]),
    ("MEMORY STACK", ["Hindsight", "PostgreSQL", "Qdrant", "MEMORY.md", "USER / SOUL"]),
    ("CHANNELS", ["Telegram", "cmux TUI", "Desktop App", "Voice (Asterisk)", "Cron Jobs"]),
    ("SUB-AGENTS", ["Delegate Tasks", "Coder Profile", "Research Profile", "Kanban Board"]),
    ("SERVICES", ["Camoufox Max", "Webtop CDP", "Bitwarden", "CF Workers", "Screen Server"]),
]

# ── Layout constants ──────────────────────────────────────────────────
ROOT_X, ROOT_Y, ROOT_W, ROOT_H = 80, 400, 180, 60
L1_X, L1_W, L1_H = 420, 220, 50
L2_X, L2_W, L2_H = 800, 190, 36
L1_GAP = 80
L2_GAP = 8
ELBOW_H = 120  # horizontal gap before first turn
ROOT_ELBOW = 80  # horizontal gap from root before turn

def build_js(branches):
    """Build JavaScript code for tldraw /api/doc/:id/exec."""
    lines = ["const {createShapeId,toRichText} = await import('tldraw');"]
    lines.append("const ids = editor.getCurrentPageShapes().map(s => s.id);")
    lines.append("if (ids.length) editor.deleteShapes(ids);")

    # Root node
    lines.append(f"editor.createShape({{id:createShapeId('root'), type:'geo', "
                 f"x:{ROOT_X}, y:{ROOT_Y}, props:{{geo:'rectangle', w:{ROOT_W}, "
                 f"h:{ROOT_H}, color:'blue', fill:'solid', "
                 f"richText:toRichText('W.ALTER\\nHARNESS')}}}});")

    # Calculate vertical centering
    total = sum(L1_H + L1_GAP + len(ch) * (L2_H + L2_GAP) for _, ch in branches) - L1_GAP
    root_mid = ROOT_Y + ROOT_H / 2
    current_y = root_mid - total / 2

    for i, (label, children) in enumerate(branches):
        l1_y = current_y
        l1_mid = l1_y + L1_H / 2

        # L1 node
        lines.append(f"editor.createShape({{id:createShapeId('l1_{i}'), "
                     f"type:'geo', x:{L1_X}, y:{l1_y}, props:{{geo:'rectangle', "
                     f"w:{L1_W}, h:{L1_H}, color:'black', fill:'solid', "
                     f"richText:toRichText('{label}')}}}});")

        # Root → L1: 3-segment elbow
        cx = ROOT_X + ROOT_W + ROOT_ELBOW
        lines.append(f"editor.createShape({{id:createShapeId('ra_{i}_h1'), type:'arrow', "
                     f"x:0, y:0, props:{{start:{{x:{ROOT_X+ROOT_W}, y:{root_mid}}}, "
                     f"end:{{x:{cx}, y:{root_mid}}}, bend:0, color:'black'}}}});")
        lines.append(f"editor.createShape({{id:createShapeId('ra_{i}_v'), type:'arrow', "
                     f"x:0, y:0, props:{{start:{{x:{cx}, y:{root_mid}}}, "
                     f"end:{{x:{cx}, y:{l1_mid}}}, bend:0, color:'black'}}}});")
        lines.append(f"editor.createShape({{id:createShapeId('ra_{i}_h2'), type:'arrow', "
                     f"x:0, y:0, props:{{start:{{x:{cx}, y:{l1_mid}}}, "
                     f"end:{{x:{L1_X}, y:{l1_mid}}}, bend:0, color:'black'}}}});")

        # L2 children
        n = len(children)
        l2_start = l1_y + L1_H/2 - (n * L2_H + (n-1) * L2_GAP) / 2
        for j, child in enumerate(children):
            l2_y = l2_start + j * (L2_H + L2_GAP)
            l2_mid = l2_y + L2_H / 2

            lines.append(f"editor.createShape({{id:createShapeId('l2_{i}_{j}'), "
                         f"type:'geo', x:{L2_X}, y:{l2_y}, props:{{geo:'rectangle', "
                         f"w:{L2_W}, h:{L2_H}, color:'grey', fill:'solid', "
                         f"richText:toRichText('{child}')}}}});")

            # L1 → L2: 3-segment elbow
            cx2 = L1_X + L1_W + ELBOW_H
            lines.append(f"editor.createShape({{id:createShapeId('aa_{i}_{j}_h1'), "
                         f"type:'arrow', x:0, y:0, props:{{start:{{x:{L1_X+L1_W}, "
                         f"y:{l1_mid}}}, end:{{x:{cx2}, y:{l1_mid}}}, bend:0, "
                         f"color:'black'}}}});")
            lines.append(f"editor.createShape({{id:createShapeId('aa_{i}_{j}_v'), "
                         f"type:'arrow', x:0, y:0, props:{{start:{{x:{cx2}, "
                         f"y:{l1_mid}}}, end:{{x:{cx2}, y:{l2_mid}}}, bend:0, "
                         f"color:'black'}}}});")
            lines.append(f"editor.createShape({{id:createShapeId('aa_{i}_{j}_h2'), "
                         f"type:'arrow', x:0, y:0, props:{{start:{{x:{cx2}, "
                         f"y:{l2_mid}}}, end:{{x:{L2_X}, y:{l2_mid}}}, bend:0, "
                         f"color:'black'}}}});")

        current_y += L1_H + L1_GAP + n * (L2_H + L2_GAP)

    lines.append("return editor.getCurrentPageShapes().length;")
    return "\n".join(lines)


def main():
    token = get_token()
    if not token:
        print("ERROR: could not read tldraw token", file=sys.stderr)
        sys.exit(1)

    # Get focused document
    result = req("api/search", {"code": "return (await api.getFocusedDoc()).id"}, token)
    doc_id = result["result"]
    print(f"Doc: {doc_id}")

    # Build and execute
    code = build_js(BRANCHES)
    print(f"{len(code.splitlines())} lines of JS…")
    result = req(f"api/doc/{doc_id}/exec", {"code": code}, token)

    if result.get("success"):
        print(f"Done. {result['result']} shapes created.")
        # Screenshot for verification
        scr = req("api/search",
                  {"code": "return JSON.stringify(await api.getScreenshot(\"" + doc_id + "\"))"},
                  token)
        fp = json.loads(scr["result"])["filePath"]
        print(f"Screenshot: {fp}")
    else:
        print(f"Error: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
