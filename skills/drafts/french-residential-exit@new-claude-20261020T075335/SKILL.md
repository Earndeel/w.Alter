---
name: french-residential-exit
description: Use when a web task needs a French (residential, non-datacenter) IP — geo-blocked French sites, anti-VPN checks — via the Freebox WireGuard exit, scoped to one browser session.
---

# French residential exit (Freebox WireGuard)

W.Alter has a WireGuard exit through the Freebox at Monsieur's parents' home: a real French residential IP,
much harder to flag than NordVPN (datacenter). It is scoped: only a browser session pointed at it uses it.

## Where things are
- Config: Bitwarden note "WireGuard – Freebox parents (VPN France)", folder "11 · Sécurité & VPN", .conf attached
  (never print it; `walter-secret file` only inside scripts).
- Exit declaration: `walter instance config browse network.toml` → `[exit.freebox-fr]`, proxy `http://127.0.0.1:1081`.
- Code: `walter path browse` + `network/wg-exit/` (README). CLI `walter-wg-exit` on the PATH.

## Rules
1. Default network stays local. Use this exit only when the task needs a French IP (explicit request or a geo-block
   confirmed by checking the exit IP first).
2. **Shared key with the Mac** (WireGuard.app tunnel "Lucas"): both can't be up at once. `walter-wg-exit up` refuses
   while the Mac is connected. Do not disconnect Monsieur's Mac tunnel yourself: ask him (or Hermes asks on Telegram).
   `--force` only when the Mac is confirmed off/unreachable and not using the tunnel.
3. Never route the host through it (no wg-quick on the host, no Tailscale exit-node changes).
4. Stop it when done: `walter-wg-exit down freebox-fr` (it is not started at boot).

## Procedure
```bash
walter-wg-exit up freebox-fr                 # prints the exit IP (should be the Freebox's French IP)
walter-browser -s fr exit freebox-fr          # on a NEW session name, before new/login
walter-browser -s fr new && walter-browser -s fr nav https://api.ipify.org   # verify the IP in-browser
# ... task (login SITE works on that session too) ...
walter-browser -s fr close; walter-wg-exit down freebox-fr
```
- curl / scripts: `curl -x "$(walter-wg-exit url freebox-fr)" ...`.
- universal_router `--network vpn --country FR` still points at nordvpn-proxy (:1080), not this exit.

## Pitfalls
- `exit` on a session that already exists in Camoufox does nothing (proxy is applied when the context is created):
  use a fresh session name and verify the IP.
- Camoufox contexts default to en-US / America/Los_Angeles: set locale/timezone expectations accordingly for
  fingerprint-sensitive French sites.
- Container fails right after `wg-quick` logs `sysctl ... src_valid_mark` then rollback = image built without the
  wg-quick patch; rebuild from `network/wg-exit/Dockerfile`.
- Kill switch is inside the container: if the tunnel drops, requests time out (no leak to the VM's IP).
