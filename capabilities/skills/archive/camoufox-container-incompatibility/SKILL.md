---
name: camoufox-container-incompatibility
category: devops
description: "Known incompatibilities when running Camoufox inside Docker containers — ESM/better-sqlite3 binding resolution failure and Firefox HOME/user ownership checks. Use Chromium CDP in containers instead."
tags: [camoufox, docker, container, webtop, firefox, esm, better-sqlite3, bindings]
---

# Camoufox Inside Docker Containers — Known Incompatibilities

## Summary

Camoufox (anti-detection Firefox wrapper) **does not work** inside Docker containers like `linuxserver/webtop`. Two blockers prevent launch:

1. **better-sqlite3 ESM binding resolution failure** — `bindings` npm package can't find native addon from ESM context
2. **Firefox HOME/user ownership check** — binary refuses to start if `$HOME` ownership doesn't match running user

**Recommendation**: Use Chromium CDP (see `webtop-chromium-cdp` skill) for containerized browser automation. Run Camoufox on the host directly (see `hermes-camoufox-setup` skill) when anti-detection is required.

## Blocker A: better-sqlite3 ESM/bindings Resolution

`camoufox-js` is ESM (`"type": "module"`). It loads `better-sqlite3` via `await import()`. `better-sqlite3` uses the `bindings` npm package which resolves the native `.node` addon by walking `Error().stack` to find the caller's `__dirname`. In ESM context, this stack walk fails — `bindings` cannot determine `module_root`.

The `.node` file **exists and loads correctly** via CJS `require()` but ESM `import()` never reaches it.

**Error signature:**
```
Could not locate the bindings file. Tried:
 → .../better-sqlite3/build/Release/better_sqlite3.node
 → ... (13 paths, all valid, all fail)
```

**What doesn't fix it:**
- `npm rebuild better-sqlite3` inside container — addon compiles fine, loads via CJS, but ESM resolution still broken
- Patching `bindings.js` with fallback paths — ESM resolution chain uses a different module instance
- Patching `better-sqlite3/lib/database.js` to bypass `bindings` — ESM module caching ignores CJS patches
- `createRequire(import.meta.url)` in camoufox-js — changes path list but `.node` load still fails
- `--require ./preload.cjs` with `Module._resolveFilename` override — CJS preload doesn't affect ESM dynamic import chain

## Blocker B: Firefox HOME/User Ownership

Firefox/Camoufox binaries check that `$HOME` is owned by the running user. In containers:

- `PUID=0` (root) → refuses: "Running as root"
- `--user abc` + `HOME=/config` → detects mismatch: "$HOME is /config which is owned by abc"
- Setting `MOZ_ALLOW_ROOT=1` does not help (Camoufox doesn't check this env var)

**Error signature:**
```
Running Camoufox as root in a regular user's session is not supported.
($HOME is /config which is owned by abc.)
```

## When Camoufox IS Needed in a Container

If anti-detection is essential (fingerprint resistance, WebGL spoofing), options:

1. **Run Camoufox on the host** — direct execution on the VPS/desktop, no container. See `hermes-camoufox-setup` skill.
2. **Webtop Chromium CDP** — less anti-detection but works in containers. See `webtop-chromium-cdp` skill.
3. **Camoufox with Xvfb on host + noVNC** — run Camoufox in Xvfb on the host, expose via noVNC for user interaction. Avoids the container issues entirely.

## Environment Tested

- Container: `lscr.io/linuxserver/webtop:ubuntu-xfce` with `--network host`
- Camoufox: v135.0.1-beta.24 (binary) + camoufox-js (Node.js wrapper)
- Node.js: v20.20.2 (nodesource, arm64)
- better-sqlite3: v11.x (native addon compiled inside container)
- Host: Ubuntu 24.04, arm64 (Oracle Cloud ARM)
