---
name: node-server-vanish-recovery
category: software-development
description: Recover a Node.js service whose dependencies vanished — distinguish "process crashed" from "files vanished" before reinstalling. Class-level recipe applicable to any standalone Node server (Express, Fastify, custom) under a project directory.
metadata:
  hermes:
    tags: [node, nodejs, npm, recovery, debugging, systemd, headless]
---

# Node Server Vanish Recovery

When a long-running Node.js service stops responding and the port is free, the instinct is to assume the process crashed. **Check first whether the files vanished.** This is a real failure mode after `rsync --delete`, checkout cleanup, npm prune misuse, or a partial git operation that left only the entrypoint behind.

## When this skill applies

- A standalone Node server (not bundled inside a parent app) stops responding.
- `systemctl status <service>` shows `failed` or `inactive`, restart loop with `MODULE_NOT_FOUND`.
- Port is free, no zombie process.
- The project directory is `~/.hermes/<service-name>/` or similar — code lives outside `node_modules` of a parent.

## The diagnostic order that matters

Most agents jump to "reinstall deps". Wrong. The right ladder is:

1. **Service state**: `systemctl status <service>` — masked? failed? restart loop?
2. **Process logs**: `journalctl -u <service> -n 50` — look for `MODULE_NOT_FOUND`, `Cannot find module`, `ENOENT`. These are the vanish signals.
3. **Filesystem inventory** — ordered from most likely to vanish to least:
   - `package.json` present? (vanishes first under `rsync --delete` because it's small and not in `.gitignore`)
   - Local helper modules under `lib/`, `src/`, etc. that the entrypoint requires? (often deleted alongside `node_modules`)
   - `node_modules/` populated? (the obvious one)
   - Browser/runtime data caches (e.g. `~/.cache/<engine>/`) for headless browser servers?
4. **Try foreground launch**: `cd <dir> && node server.js` — read the FIRST error line. It tells you which layer is missing.
5. **Patch the missing layer, restart**.

## The "vanish hierarchy" — why files disappear in this order

| Likelihood | File | Why it vanishes |
|---|---|---|
| Highest | `package.json` | Small, not in `.gitignore`, often regenerated and forgotten |
| High | `lib/*.js` local helpers | Auxiliary files separated from main entrypoint, lost in selective sync |
| High | `node_modules/` | Frequently excluded then nobody reinstalls |
| Medium | Runtime data caches (`~/.cache/...`) | OS cache cleanup, low disk pressure |
| Lowest | The entrypoint `server.js` | Big enough to notice, usually in version control |

If you see ONLY the entrypoint in the directory and nothing else, you are in vanish-territory. Don't assume it's the entrypoint that's broken.

## Recovery recipe

1. **Recreate `package.json`** — pin known-good versions. Keep it minimal:
   ```json
   {
     "name": "<service-name>",
     "version": "1.0.0",
     "main": "server.js",
     "dependencies": {
       "<runtime-lib>": "^<version>",
       "express": "^4.21.0",
       "dotenv": "^16.4.5"
     }
   }
   ```

2. **Recreate missing local helpers** — read the entrypoint's `require('./lib/*')` lines, reconstruct minimal stubs that match the call sites. A passthrough stub is often enough to restore service; refine later.

3. **`npm install --no-audit --no-fund`** — reinstalls deps. ~15s for a typical headless browser server.

4. **Re-fetch runtime data** if needed — e.g. browser binaries via the package's own fetch CLI (`node node_modules/<pkg>/dist/__main__.js fetch`).

5. **Test in foreground first**: launch manually before restarting the service. If it boots, `systemctl restart <service>` will too.

## Anti-pattern: assume "the process crashed"

Don't run `journalctl --since "1 hour ago" | grep -i error` and stop there. If the process never STARTED, there's no runtime error to find. Look for `MODULE_NOT_FOUND` at startup, not segfaults during operation.

## Anti-pattern: blanket `npm install` without `package.json`

`npm install` with no `package.json` populates a barebones `node_modules/` based on what's in `package-lock.json` (if present) or nothing. It silently "succeeds" and you'll waste another cycle wondering why the server still can't find the module.

## Pitfalls

- **Dependencies have their own data caches** — for headless browser libs (Camoufox, Puppeteer, Playwright), reinstalling node_modules does NOT redownload the browser binary. Check the cache directory separately.
- **Lock files lie** — if `package-lock.json` was committed but `package.json` wasn't, npm reinstalls FROM the lock and you get the right tree. If both vanished, you have to reconstruct the dep list from `require()` statements in the source.
- **The systemd unit may be masked** — if `systemctl status` says `masked`, the service can't be started by anyone. `systemctl unmask <service>` lifts it. Common after a crash loop where `Start request repeated too quickly` triggered an admin masking step.
- **EnvironmentFile must use `=-/path` (with dash)** in unit files if the env file may not exist yet — otherwise systemd refuses to start when the file is absent.
- **`After=tailscaled.service`** on services whose stealth profile depends on a Tailscale exit node: without it, the service may start before tailscaled is up and leak the wrong egress IP.

## Verification checklist

- [ ] Service `active (running)` and `enabled` for autostart
- [ ] Health endpoint responds
- [ ] Process survives a deliberate `systemctl restart`
- [ ] Process survives a deliberate `kill -9` (Restart=on-failure kicks in)
- [ ] Logs go where the unit says they go
- [ ] If stealth-dependent: egress IP check matches expectation

## Related skills

- `hermes-camoufox-setup` — applies this recipe to the Camoufox headless browser specifically.
- `systemd-crash-loop-recovery` — diagnoses and recovers from "Start request repeated too quickly" masking.
- `agent-loop-prevention` — when the same diagnostic step keeps failing, stop and re-examine assumptions instead of retrying.
