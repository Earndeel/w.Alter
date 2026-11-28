---
name: node-service-debugging
description: "Expert Node.js service operations: Chrome DevTools Protocol (CDP) debugging, dependency recovery, server-vanish diagnostic patterns, and lockfile synchronization."
version: 1.0.0
author: Orchestra Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Node, Node.js, NPM, Debugging, Chrome DevTools Protocol, CDP, Inspector, Troubleshooting]
---

# Node.js Service Debugging & Recovery

A consolidated class-level skill covering runtime debugging, Chrome DevTools Protocol inspection, and server restoration workflows when package environments or dependencies regress.

---

## 1. Remote Debugging with --inspect

Node.js has built-in debugging support via the Chrome DevTools Protocol (CDP).

### Starting Node in Debug Mode
To start a service allowing remote attachment of a debugger:
```bash
# Start with debugger listening on local port 9229
node --inspect=127.0.0.1:9229 index.js

# Break at start of execution to debug startup issues
node --inspect-brk=127.0.0.1:9229 index.js
```

### Accessing the Inspector
1. Open a Chromium-based browser (Brave/Chrome/Edge).
2. Navigate to `chrome://inspect`.
3. Locate the Node target and click **"Inspect"** to open dedicated DevTools.

---

## 2. Dependency Restoration & "Vanished Server" Recovery

When a Node.js process suddenly crashes due to missing dependencies, or when packages are wiped during package upgrades, execute the structured recovery procedure.

### Diagnostics Checklist
1. Inspect the stack trace for `Error: Cannot find module '<package>'`.
2. Inspect `package.json` vs `package-lock.json` or `pnpm-lock.yaml` for version mismatches.
3. Check `node_modules/` existence and content.

### Safe Restoration Commands
```bash
# 1. Clean stale build artifacts/caches
npm cache clean --force

# 2. Perform a fresh, clean install
rm -rf node_modules package-lock.json
npm install
```

---

## Support Directory Map
- `references/inspect-debugger.md`: Chrome DevTools Protocol (CDP) deep-dive, command-line inspector scripts, and secure tunnel setup.
- `references/server-vanish-recovery.md`: In-depth disaster recovery steps for missing dependency modules, broken scripts, and package regressions.
