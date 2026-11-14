# NordVPN CLI on Linux — install, login traps, connect

Verified against NordVPN 5.3.0 on the VPS host (2026-08).

## Install (apt-based official script)

The official script prompts `Do you want to continue? [Y/n]` → pipe `yes`:

```bash
yes | sh <(curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh)
nordvpn version
```

Installs the daemon `nordvpnd` + client `nordvpn` + `nordvpn-gui` + `xsltproc` (~160 MB on disk).

## Login: browser-OAuth ONLY

NordVPN Linux v5.x has **no username/password login mode** (the legacy `--nordaccount` flag is removed).
The only paths are browser OAuth (`nordvpn login`) and `--token` (no MFA, revoked at logout).

```bash
printf 'n\n' | nordvpn login
# → prints: Continue in the browser: https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=...
```

Key traps discovered:
- **The analytics-consent prompt MUST get an answer.** Running `nordvpn login` with closed/empty stdin
  re-prompts "Do you allow us to collect..." in an infinite loop; a redirected log ballooned to 1.2 GB
  in minutes. Pipe `printf 'n\n'` first.
- **The client process opens no listen port** — it mints an OAuth URL and waits for the browser flow.
  The daemon (`nordvpnd`) holds state; `nordvpn login` simply waits.
- **~120 s timeout.** The login client exits after about two minutes if the browser flow isn't completed.
  Complete the browser login while the process is alive, or finish manually with
  `nordvpn login --callback "<url>"`.
- **Do NOT `pkill -f "nordvpn login"`** to clean up: the pattern matches the pkill command line itself and
  kills your own launching shell (observed: background job died with exit -9 after doing exactly this).
  Match tighter (`pgrep -f 'nordvpn login'` → kill by PID) or just let the timeout expire.
- Log files: the first runaway loop left `/tmp/nordlogin.log` at ~1.2 GB — always delete it after cleanup.

## Connect / status / disconnect

```bash
nordvpn c France          # or: nordvpn connect fr / 'nordvpn connect Paris'
nordvpn status            # → "Connected" / "Disconnected"
nordvpn d                 # disconnect
```

## Verify the exit actually changed

```bash
curl -s --max-time 8 https://ifconfig.me
```
Expect a French IP/range after `nordvpn c France`. Then hit the target portal from the intended exit:
`assure.ameli.fr` / `www.ameli.fr` must answer HTTP (not 000/403) once the exit is French.

In practice, the ~10 s "Mac VPN app connected to France" path (since the webtop egresses via the Mac
Tailscale exit node) beat all server-side effort — prefer it whenever the Mac app is available.
