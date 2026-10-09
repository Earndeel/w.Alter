---
name: tldraw-workflows
description: Use when automating or diagramming in tldraw.
tags: [tldraw, diagramming, automation, canvas, connectors]
metadata:
  hermes:
    tags: [tldraw, diagramming, automation, canvas, connectors]
---

# tldraw Workflows

Use this class-level skill for structured diagram generation and remote tldraw automation. Load the separately maintained tldraw-offline API procedure when the canvas is not already installed and verified.

## Remote operation

When Hermes runs remotely, use a single SSH tunnel to the Mac tldraw API, cache the token only as required by the active session, re-read it after an app restart, and close disposable tabs/resources in a finalizer. Verify screenshots through the API and move remote files locally before visual analysis.

## Canvas rules

Use `editor` plus `helpers` in `/api/doc/:id/exec`; use the broader `/api/search` scope for screenshots and other `api.*` methods. Do not pass unsupported `fontSize` or internal `handles` properties. Use `arrow` shapes for connectors; true elbows require three straight segments with shared endpoints rather than a Bézier `bend`.

Generate nodes from explicit layout constants, create stable IDs, and verify the rendered screenshot. If tldraw is installed and working, use it for diagramming rather than switching tools without a capability failure.

Exact historical API, tunnel, and layout recipes are routed in `references/curator-tldraw-archive-routes.md`.
