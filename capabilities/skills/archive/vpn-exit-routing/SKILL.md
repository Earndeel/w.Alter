---
name: vpn-exit-routing
description: Use when a portal geo-blocks your exit IP; route via VPN.
version: 1.0.0
author: W.Alter
license: Proprietary
metadata:
  hermes:
    tags: [vpn, geo-block, exit-node, nordvpn, ameli, tailscale, browsing]
    related_skills: [webtop-authenticated-browsing, web-service-browser, mac-remote-access-package]
---

# VPN Exit Routing (geo-blocked portals)

Use when a portal/service refuses connections from the current exit IPs and you need a specific
country's exit (typically France for French government portals like Ameli).

## Core principle: verify geography BEFORE touching cookies/auth

Some portals geo-block at the network layer — TCP reset / `ERR_CONNECTION_REFUSED` from every exit —
not at the auth layer. Diagnosing this first saves the whole cookie-extraction pipeline.

## Core rule (user correction, 2026-08): VPN never touches the host — only the browser

When the web target needs a specific exit country, the VPN must be confined to the
**browser/container layer**. Connecting NordVPN on the Linux host (`nordvpn connect France`)
rewrites host routing and **breaks Tailscale** — the SSH path to the Mac and the webtop's
`network_mode=host` exit both die. Monsieur: "tu devais utiliser le vpn que sur le camoufox."

Correct architecture: a dedicated bridge-network container (`nordvpn-proxy`) runs NordVPN +
microsocks (SOCKS5 on `127.0.0.1:1080`), and ONLY the browser is pointed at that proxy
(Playwright `--proxy-server=socks5://127.0.0.1:1080`). Host stays on Tailscale + its normal route.
Full verified recipe: `references/nordvpn-container-proxy.md`.

Quick sanity check after setup (host IP unchanged, proxy IP = target country):
```bash
curl -s --max-time 8 https://ifconfig.me                                     # host: unchanged
curl -s --max-time 8 --socks5 <user>:<pass>@127.0.0.1:1080 https://ifconfig.me  # proxy: target country
```

Confirmed 2026-08 (Ameli / assurance maladie):
- `assure.ameli.fr` refused TCP on 443 from Thailand (Mac), Singapore (VPS), and the webtop.
- `www.ameli.fr` answered 301/403 to non-browser clients.
- Cookies were freshly decryptable (OIDC/session tokens present) yet useless — the network never
  reached the server. Geo, not auth.

## Procedure

1. **Geographic check first** (cheap, decisive):
   ```bash
   docker exec webtop curl -s --max-time 8 https://ifconfig.me       # webtop real exit
   curl -s --max-time 8 https://ifconfig.me                            # VPS host exit
   timeout 20 ssh lucasjouvencon@100.127.150.1 'curl -s --max-time 8 https://ifconfig.me'  # Mac exit
   curl -s -o /dev/null -w "%{http_code}\n" --max-time 12 https://<portal>
   ```
   `000`/`Connection refused` from every exit = geo-block. Stop hitting the portal; fix geography.
2. **Check for a lightweight existing exit.** Is the Mac a Tailscale exit node for the webtop?
   `tailscale set --exit-node=<mac>` / `tailscale status`. If so, the Mac IS the webtop's de-facto
   exit → prefer the next step.
3. **Quickest path: VPN app on the Mac (when Mac is Tailscale exit node).**
   Since webtop traffic egresses via the Mac, having the user connect the vendor app (e.g.
   `NordVPN.app`) to the target country re-exports ALL webtop traffic through that geography in ~10 s —
   zero server-side VPN setup, no password handled by the agent. Prefer this before building server-side
   VPN. Flag the side effect: the Mac's own global traffic rides the VPN for that session.
4. **Server-side fallback: NordVPN in a dedicated proxy container** (NOT on the host — host-level
   CLI breaks Tailscale routing; see Core rule above). Build `nordvpn-proxy` bridge container with
   NordVPN + microsocks SOCKS5, verify `curl --socks5 127.0.0.1:1080 ifconfig.me` shows the target
   country while the host IP is unchanged. Full recipe in `references/nordvpn-container-proxy.md`
   (`references/nordvpn-linux-cli.md` has the CLI login-flow traps).
5. **Re-run the geographic check from the intended exit** before wiring any auth/cookie work, then
   proceed with the normal authenticated-browsing pipeline.

## Pitfalls

- **`pkill -f "nordvpn login"` kills its own launching shell** — the pattern matches the pkill command
  line itself. Match tighter (`pgrep -f 'nordvpn login'`), kill by PID, or let the CLI timeout expire.
- **NordVPN Linux login is browser-OAuth only** — no username/password mode in v5.x (legacy
  `--nordaccount` removed). It mints an OAuth URL and waits; the client process opens no listen port and
  exits ~120 s later. Do the browser step while it lives, or complete with `--callback "<url>"`.
- **The analytics-consent prompt must be answered** (`printf 'n\n' | nordvpn login`). With closed stdin
  it re-prompts in an infinite loop; the redirected log ballooned to 1.2 GB in minutes.
- **Do not inject fingerprint-bound anti-bot cookies** (Akamai `TS*`, `BIGip*`) from another exit —
  they're bound to the source fingerprint. Move only the auth/session cookies (Ameli set:
  `JSESSIONID`, `_WL_AUTHCOOKIE_JSESSIONID`, `mod_auth_openidc_session`, `ASpersist`, `ameli_espace`).
- Some portals answer 403 to non-browser clients even from a correct country — that is a fingerprint/
  anti-bot symptom, separate from geo-blocking.

## Completion checklist

- [ ] Geo-block confirmed (or excluded) with actual exit IP per hop.
- [ ] Correct-country exit established (Mac VPN app or server-side VPN) and re-verified via ifconfig.me.
- [ ] Cookie/auth work only attempted after exit geography is correct.
- [ ] Side-effect of Mac-wide VPN routing disclosed to the user.

## Browser-through-proxy and Turnstile notes (2026-08)

- **Chromium/Chrome does not support SOCKS5 proxy authentication** (`BrowserType.launch: Browser does not support socks5 proxy authentication`). Use a no-auth SOCKS5 (microsocks with `-w <ips>` whitelist — note `-w` REQUIRES `-u/-P` to be present; whitelisted sources bypass auth) or an HTTP proxy (tinyproxy) pointing at the same container.
- **HTTPS through the container proxy: use tinyproxy HTTP + Camoufox — validated 2026-08-11.** Chrome/Chromium over SOCKS5+docker-proxy fails the TLS handshake (`net_error -100`/timeout) while curl succeeds; HTTP-only sites pass in Chrome. The working stack for HTTPS/Turnstile pages is **Camoufox (PyCamoufox) pointed at `http://127.0.0.1:1080` (tinyproxy)** — verified loading `my.oneforma.com` with `cfChallenge:false` and French exit IP. Do not burn time on Chrome-over-SOCKS5 TLS: switch the browser to the HTTP proxy path.
- **Diagnose container-proxy outages in this order: (1) Tailscale exit node, (2) ip rules, (3) FORWARD.** On 2026-08-11 the proxy container lost ALL outbound after a `docker restart`; several rounds of FORWARD/`ip rule` repair made no progress because the real cause was a leftover `tailscale set --exit-node=<mac>` — an active exit node breaks every docker bridge container's networking (SYN sent, no reply), masquerading as an iptables fault. Check `tailscale status | grep "exit node"` and clear with `tailscale set --exit-node=""` BEFORE touching rules. Then re-apply the two recreate-lost fixes (see `references/nordvpn-container-proxy.md`): host FORWARD+DOCKER-USER ACCEPT for `172.17.0.4:1080` + `ctstate ESTABLISHED,RELATED`, and inside the container `ip rule add pref 100 from 172.17.0.0/16 lookup main` + `pref 101 to 172.17.0.0/16 lookup main` (NordVPN re-adds `not from all fwmark 0xe1f1 lookup 205` on connect, which swallows SYNACK replies to the bridge).
- Cloudflare **managed Turnstile is fingerprint-bound**: injecting `cf_clearance` from another browser instance is rejected. Resolve the challenge inside the SAME persistent profile (webtop Chromium `--user-data-dir=/tmp/chrome-cdp-profile`, CDP 9224, windowed `DISPLAY=:1`); click the widget then reload in-place. Never relaunch a fresh profile per attempt. For headless anti-detect, Camoufox + tinyproxy-HTTP is the alternative that sidesteps the human Turnstile entirely (it earns its own clearance).
- OneForma (`my.oneforma.com`) specifics: the login SPA is Turnstile-gated; `Sign in with Google` (Mac Brave Google cookies) is the cleaner route — the account chooser lists linked identities and the resulting `?type=LINK_CONFIRMATION&provider=google&socialId=...` URL confirms the association before any captcha. The visible "Verify you are human" checkbox sits LEFT of its container (≈372,337 at 1600×1000), not at container center.

Detail appended to `references/nordvpn-container-proxy.md` (microsocks `-w` flag combo, tinyproxy config, Chromium socks5-auth limitation, Turnstile same-profile rule, OneForma LINK_CONFIRMATION flow).

## browser-use × Camoufox (validated 2026-08-11) — reference

For LLM-scripted interaction (the "browser_exec" idea from the Nous Research
tweet) on top of stealth Camoufox + the French proxy: `references/browser-use-camoufox.md`.
Key facts: browser-use **0.4.5** (Playwright-native, `Browser = PlaywrightBrowser |
PatchrightBrowser`) accepts `Agent(browser=camoufox_obj)` — later versions
(0.5.x–0.13.x / CLI 3.0) are BrowserSession/CDP-only and can NEVER drive
Firefox/Camoufox. Isolated venv `/root/.venv/bu-legacy`, pin `openai==1.85.0`.
OneForma smoke task passes without Turnstile blocking. Routing decision: this is
an optional backend between camoufox-max and webtop in the walter_browse chain —
never the default for structured extraction.
