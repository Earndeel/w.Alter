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
