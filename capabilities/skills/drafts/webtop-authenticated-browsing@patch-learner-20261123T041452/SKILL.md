---
name: webtop-authenticated-browsing
description: "Authenticated browsing via Camoufox or Webtop Chromium with Mac Brave cookies. Cookie extraction, injection, anti-detect navigation, screenshots, click/scroll/keyboard interaction. Also covers: webtop chromium cdp."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [browser, cdp, cookies, auth, camoufox, webtop, brave, mac, anti-detect]
    related_skills: [hermes-camoufox-setup, playwright-cdp-browser-control]
---

# Webtop Authenticated Browsing

> **State on 2026-11-01.** To act as Monsieur on a site, the normal path is `walter_browse` (Hermes) or `browser_session` + `walter-browser` (Claude Code, Codex, DSH): his cookies are injected server-side and the agent only gets metadata. Never extract Brave cookies, keychain keys or LevelDB yourself; the extraction steps below are history and debugging material. Entry: `walter-browse-orchestrator`.

Browse sites where Lucas is logged in on Mac Brave, using anti-detect Camoufox or Webtop Chromium with injected cookies. Covers the full pipeline: extract → inject → navigate → interact → screenshot.

## Always-on rules

- When Monsieur says "ouvre le moi" — open it on his Mac Brave via SSH immediately. Don't suggest Webtop URLs or give instructions. Just do it.
- NEVER connect Scrapling/Playwright to main Mac Brave CDP (port 9226).
- Use Camoufox (localhost:9377) or Webtop Chromium (localhost:9223) for all browsing.
- The Mac Brave CDP is ONLY for cookie extraction (Step 1) via raw `websockets` + `Storage.getCookies`, never for navigation.
- NEVER inject `cf_clearance` from one browser into another.
- Inject ONLY auth cookies (session tokens, Keycloak, PHPSESSID), then let the target browser navigate to the site and obtain its OWN `cf_clearance` automatically.
- Preferred: Keychain decryption (works when main Brave has no CDP — which is the normal case).
- Refs reset after navigation: Must re-snapshot before clicking in Camoufox.
- Always `SIGTERM` first, wait 30s, then `SIGKILL` as fallback.
- Selkies requires HTTPS: Use `https://<host>:3001` instead.

## When to Use

- Need to browse a site where Lucas has an active session on Mac Brave
- Scrapling/headless tools get blocked by anti-bot (Facebook, Cloudflare, etc.)
- Need screenshots + click/scroll/keyboard interaction on authenticated pages
- Need human-like browsing behavior (not API calls)

## Step 3: Screenshot + Analysis Pattern

```python
# At each interaction step, screenshot + vision_analyze
page.screenshot(path="/tmp/step-N.png")
# Use vision_analyze tool on /tmp/step-N.png to understand what's visible
# Use snapshot (accessibility tree) to find clickable refs
```

## Account-Risk Policy

- Prefer **Camoufox/browser navigation** over internal API calls
- Do NOT create cron polling jobs against unofficial APIs
- Do NOT send messages through internal APIs unless Monsieur accepts risk
- Read-only, one-shot checks only, on user request
- Tinder: `localStorage.getItem('TinderWeb/APIToken')`, API `api.gotinder.com`, no mass scraping

## References (read with skill_read(name, file_path=...))

- `references/camoufox-host.md` — Read when starting or controlling host Camoufox, importing cookies through its API, or using behavioral simulation and CAPTCHA modules.
- `references/cookie-extraction.md` — Read before extracting or injecting Mac Brave cookies, converting expiry timestamps, or handling SQLite and Keychain fallbacks.
- `references/macos-cookie-decryption.md` — Read for detailed macOS cookie decryption analysis, encryption scheme details, and Keychain access methods.
- `references/northwest-registered-agent.md` — Read when browsing Northwest Registered Agent for its Keycloak authentication flow, SPA behavior, and document download patterns.
- `references/routing-and-verification.md` — Read when choosing the browser and visibility path, coordinating cookie extraction with browser setup, or verifying the session.
- `references/site-workflows-and-downloads.md` — Read for Google Flow, Facebook, Instagram, or LinkedIn workflows, or when capturing S3/CDN download URLs.
- `references/troubleshooting.md` — Read when diagnosing browser, cookie, CDP, Cloudflare, container, display, or Keychain failures.
- `references/webtop-browsers.md` — Read when launching visible browsers in Webtop, choosing noVNC or Selkies setup, using Chromium CDP, or managing browser persistence.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **webtop-authenticated-browsing** — Webtop container administration: Chromium + CDP startup script, stale Singleton locks, s6-overlay boot service, cron persistence, verifying browser access.
  Read `references/merged-webtop-chromium-cdp/webtop-authenticated-browsing.md`.

## Vérifier la sortie France commune à Camoufox et Chromium

Avant une navigation authentifiée, vérifier la route active : les deux moteurs utilisent le sélecteur SOCKS `127.0.0.1:1083`. Le sélecteur choisit le Mac uniquement lorsque son tunnel WireGuard « Lucas » est connecté ; sinon il démarre la sortie `freebox-fr`. Si aucune route ne fonctionne, les connexions doivent échouer, sans sortie directe par la VM.

1. Contrôler les services et les journaux :
   ```bash
   systemctl status walter-exit-default camoufox-max --no-pager
   journalctl -u walter-exit-default -n 30 --no-pager
   ```
2. Vérifier la sortie effective du sélecteur :
   ```bash
   curl --fail --silent --show-error --max-time 15 --proxy socks5h://127.0.0.1:1083 https://api.ipify.org
   ```
   Comparer avec la sortie France attendue dans la configuration courante ; ne pas conclure à partir du seul état « active » de systemd.
3. Vérifier chaque moteur avec une session temporaire distincte :
   ```bash
   for engine in camoufox chromium; do
     session="route-check-$engine"
     /opt/walter-core/bin/walter-browser -e "$engine" -s "$session" new
     /opt/walter-core/bin/walter-browser -e "$engine" -s "$session" nav https://api.ipify.org
     /opt/walter-core/bin/walter-browser -e "$engine" -s "$session" eval "({ip:document.body.innerText,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,languages:navigator.languages})"
     /opt/walter-core/bin/walter-browser -e "$engine" -s "$session" close
   done
   ```
   Vérifier la sortie France, `Europe/Paris` et les langues françaises puis anglaises.

Ne jamais activer simultanément le tunnel Lucas du Mac et le tunnel de secours utilisant la même clé WireGuard : laisser le sélecteur gérer leur exclusion. Ne pas modifier le VPN du Mac pour ce contrôle.

Si les journaux signalent `walter-secret file failed` ou `bw list failed`, vérifier `systemctl is-active walter-secrets-sync`, puis `walter-secret search wireguard freebox` sans afficher de valeurs secrètes. Comparer l’utilisateur et l’environnement du service avec ceux de l’appel manuel ; l’unité installée pendant cette session a nécessité `User=root`. Ne pas contourner cet échec en inscrivant une clé dans l’unité systemd. Refermer les sessions temporaires même si une vérification échoue.

## Diagnose Camoufox stalls before benchmarking parallel tabs

1. Check the live service and its memory limits before increasing concurrency. Use the running unit's `ExecStart` to find the active server code; do not assume the Browse source checkout is what systemd is running.

```bash
systemctl show camoufox-max -p ExecStart -p ControlGroup -p MemoryCurrent -p MemoryHigh -p MemoryMax -p MemorySwapCurrent -p MemorySwapMax
systemctl cat camoufox-max
curl -fsS --max-time 10 http://127.0.0.1:9377/health
journalctl -u camoufox-max --since '10 min ago' --no-pager | tail -40
```

On Monsieur's VM, inspect `/etc/systemd/system/camoufox-max.service.d/10-memory-guard.conf` for the configured guard. On cgroup v2, compare memory and swap usage and take `memory.events` readings before and after the run to detect throttling or limit hits:

```bash
CG=$(systemctl show camoufox-max -p ControlGroup --value)
if [ -n "$CG" ]; then
  for f in memory.current memory.max memory.swap.current memory.events; do
    p="/sys/fs/cgroup${CG}/$f"
    if [ -r "$p" ]; then printf '\n%s\n' "$f"; cat "$p"; fi
  done
fi
```

2. Use a dedicated authenticated test session and the same fixed URL set for each run. Record discovery and detail extraction separately. For detail extraction, measure a one-tab baseline, then test two tabs and increase only while the service has headroom. Use a bounded worker pool and assign each worker its own tab ID; concurrent navigation through one shared tab is not a parallel-tab test. Confirm the tab routes and payloads in the live server code and `/opt/walter-core/bin/walter-browser` before scripting them. Set per-request timeouts and record wall time, successful reads, failures, and memory and swap usage. Do not compare serial browser navigation with batched API extraction as if both were running at their best concurrency.

3. If parallel navigation times out while the service is at its memory ceiling and using swap, stop increasing concurrency. Report memory pressure as the leading diagnosis, not proof of a per-session lock or proof that more memory will fix it. Close only the session created for the benchmark, then rerun the health and memory checks. For the session used in this test:

```bash
/opt/walter-core/bin/walter-browser -s fbm-par close
curl -fsS --max-time 10 http://127.0.0.1:9377/health
systemctl show camoufox-max -p MemoryCurrent -p MemorySwapCurrent
```

If CLI cleanup fails, verify the live server exposes `DELETE /sessions/:id` before using `curl -fsS --max-time 60 -X DELETE http://127.0.0.1:9377/sessions/fbm-par` for that test session. Do not guess a `POST /session/close` route. Obtain approval before changing the memory guard or restarting the shared service, then rerun the same fixed workload to confirm any improvement.
