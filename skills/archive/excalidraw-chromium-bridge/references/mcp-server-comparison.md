# Excalidraw Delivery Methods Comparison

Tested 2026-06-29. Covers all delivery paths for Excalidraw diagrams from W.Alter.

## Methods

### 1. Static `.excalidraw` File
- Generate JSON → save via `write_file` → user drag-drops on excalidraw.com
- **Best for:** One-off diagrams, sharing via file
- **No dependencies:** JSON only, no server needed

### 2. ExcaliDash API (draw.walter-ai.cloud)
- Generate JSON → POST to ExcaliDash API → instant collaborative board
- **Best for:** Live collaboration, multi-board management, iteration
- **Dependencies:** ExcaliDash running (Docker: frontend :6767 + backend :8000)
- **Credentials:** `lucas@walter-ai.cloud` / `«secret:vault»`
- **API flow:** GET `/api/csrf-token` → POST `/api/auth/login` → POST `/api/drawings`
- **Note:** In-memory storage. Server restart clears boards.

### 3. MCP Server (mcp_excalidraw)
- Canvas server (port 3000) + MCP tools (26 total) over stdio
- **Best for:** Agent-driven iterative refinement (draw → `describe_scene` → adjust)
- **Dependencies:** Node.js 18+, full frontend build (Vite)
- **Pitfall:** `create_from_mermaid` needs the full frontend (Vite build), not just canvas-only Docker image
- **Pitfall:** Canvas-only Docker (`ghcr.io/yctimlin/mcp_excalidraw-canvas:latest`) supports REST API but NOT Mermaid conversion
- **Verdict:** Overkill for mindmaps. Adds value for feedback-loop workflows.

### 4. Excalidraw.com Rooms (Chromium bridge)
- Open collaborative room → inject via React fiber traversal → broadcastScene
- **Best for:** When user is already in an Excalidraw room
- **Dependencies:** Playwright Chromium, camoufox-max (for screenshots)
- **Pitfall:** Rooms MERGE elements — cannot clean/reset reliably

### 5. Official Excalidraw Docker (`excalidraw/excalidraw`)
- Run official image → open in browser → ???
- **Best for:** NOTHING (headless). Only useful if a human manually opens the browser.
- **Dependencies:** Docker, port mapping, browser
- **Status:** ❌ UNSUITABLE for programmatic use
- **Why:** Pure client-side React SPA. No server-side API, no `loadScene()`, no persistence path. `updateScene()` modifies React state but canvas never re-paints headless. Clipboard paste clips payloads. localStorage/IndexedDB injection fails. See `excalidraw-chromium-bridge` pitfall #24 for full test matrix (15 approaches, all failed).
- **Verdict:** Do NOT use for automation. Use ExcaliDash or rooms instead.

## Decision Matrix

| Criterion | Static | ExcaliDash | MCP Server | Room | Official Docker |
|-----------|--------|------------|------------|------|----------------|
| Setup effort | None | Medium | High | Medium | Low |
| Live preview | ❌ | ✅ | ✅ | ✅ | ⚠️ Manual only |
| Multi-board | ❌ | ✅ | ❌ | ❌ | ❌ |
| Pill nodes + elbow arrows | ✅ | ✅ | ❌ | ✅ | ❌ (no API) |
| Mermaid import | ❌ | ❌ | ✅ (needs frontend) | ❌ | ❌ |
| IA feedback loop | ❌ | ❌ | ✅ `describe_scene` | ⚠️ Screenshot only | ❌ |
| Collaboration | ❌ | ✅ | ✅ | ✅ | ⚠️ Manual only |
| Headless automation | ✅ (file only) | ✅ REST API | ✅ MCP stdio | ✅ Fiber + broadcast | ❌ BROKEN |

## Recommendation

**For clean mindmaps:** JSON direct → ExcaliDash API (Mode 4 in `excalidraw` skill).
Mermaid auto-layout produces generic diagrams without pill nodes, elbow routing, or custom color palettes.

**Do NOT use `excalidraw/excalidraw` Docker for headless automation.** It's a client-side SPA with no programmatic entry point. 15 tested approaches all failed (see pitfall #24 in `excalidraw-chromium-bridge`).
