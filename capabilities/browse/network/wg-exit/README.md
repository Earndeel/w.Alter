# wg-exit — scoped WireGuard exits for browser sessions

A WireGuard client config (from the vault) runs inside its own container and is offered to the host
as an HTTP proxy on `127.0.0.1:<port>`. Only clients pointed at that proxy use the tunnel: host routing,
Tailscale and every other session stay local (rule: a VPN is never W.Alter's global route).

- Exits are declared by the instance: `walter instance config browse network.toml` (`[exit.<name>]`:
  `port`, `country`, `secret` = vault item, `attachment` = the .conf, optional `shared_with`).
- `walter-wg-exit list | up NAME [--force] | down NAME | status [NAME] | url NAME`.
- Browser: `walter-browser -s <session> exit <name>` on a **new** session, then `new`/`nav` as usual.
- `shared_with = { ssh = "<host>", macos_vpn = "<tunnel>" }`: the key is also used by that device;
  `up` refuses while it is connected there (two peers with one key knock each other off), and refuses
  when the device cannot be checked unless `--force`.
- The .conf goes vault → tmpfs → container, and is deleted once the tunnel is up (keys only in the kernel).
  Kill switch: inside the container, eth0 only carries the tunnel's UDP and replies to the host.
- `/proc/sys` is read-only in a container, so the image removes wg-quick's `sysctl src_valid_mark`
  call and `docker run --sysctl` sets it instead (without that, wg-quick rolls the tunnel back).
- Not started at boot (`--restart no`), on purpose: start it for the task, stop it after. Exception: the
  default exit's fallback is started and stopped by `walter-exit-default` (`../exit-default`).

## Provider NordVPN (2026-11-11)

- Exits `nordvpn-<cc>` are not declared one by one: `[provider.nordvpn]` in the instance's `network.toml` points at
  the service settings (`/services/nordvpn-proxy/config/service.toml`) and the grant (`nordvpn`, reader `browse`).
- `walter-wg-exit countries` (live list from the public API) ; `use NAME` (opens if needed, prints only the proxy URL
  on stdout) ; `up/down/status/url` work on `nordvpn-<cc>` too.
- Port = `port_base` + NordVPN country id (fixed per country: a session never changes country silently);
  `max_exits` at once.
- `up`: token → NordLynx private key (credentials API, never stored) → recommended server for the country → conf in
  tmpfs (O_EXCL, 0600) → container `walter-wg-nordvpn-<cc>` (labels `walter.provider/country/server`), same kill switch.
  Then the tunnel is checked from inside (insights: `protected`, country); otherwise the container is removed.
  API calls ignore any proxy variables of the caller.
- `up` (when it replaces a container) and `down` call the engine's `POST /exits/reset` first: browser and sessions on
  that port are closed, so no session keeps the identity of the previous NordVPN server.
- Tests: `tests/killswitch-dead-tunnel.sh <country-id>` (no token needed: a random key against a real server, the
  tunnel never comes up, nothing may leave — proxy, DNS, direct TCP, even with wg0 deleted) ;
  `tests/nordvpn-live.sh [A] [B]` (real: browser on A, IP/country/protected, WebRTC, MCP read, second country B,
  bypass refusals, DNS capture, tunnel cut, release, other exits unchanged).

