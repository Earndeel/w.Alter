---
name: tailscale-docker-access
category: devops
description: Access Docker container ports from Tailscale peers when iptables blocks direct access. SSH tunnel workaround for ts-input chain conflicts.
tags: [tailscale, docker, iptables, networking, ssh-tunnel]
---

# Tailscale → Docker Port Access

## Problem
Docker containers bind ports on `0.0.0.0` (verified via `docker exec <container> ss -tlnp`), but accessing via Tailscale IP times out. Localhost access from host may also hang — TCP connects but HTTP never responds (symptom of docker-proxy issue, see Root Cause #2).

## Diagnosis
```python
# Run on host — compare localhost vs Tailscale IP reachability
import socket
for host in ['127.0.0.1', '<tailscale-ip>']:
    s = socket.socket(); s.settimeout(3)
    try: s.connect((host, <port>)); print(f'{host}:<port> OPEN')
    except Exception as e: print(f'{host}:<port> {e}')
    finally: s.close()
```

If localhost works but Tailscale IP times out → iptables issue.

## Root Cause #1: Tailscale iptables
Tailscale injects `ts-input` chain at top of `iptables INPUT`. Key rules:
```
ACCEPT  --  tailscale0 *  0.0.0.0/0  0.0.0.0/0         # accept all via tailscale0
DROP    --  !tailscale0 *  100.64.0.0/10  0.0.0.0/0     # drop Tailscale-sourced from other ifaces
```
Docker DNAT rewrites destination to container IP (172.17.0.x), but the return path or intermediate routing may cause packets to arrive via a non-tailscale0 interface, triggering the DROP rule.

Verify with: `iptables -L ts-input -n -v`

## Root Cause #2: docker-proxy + systemd socket activation (MORE COMMON)
When Docker starts via systemd socket (`docker.socket` active → check with `systemctl status docker.socket`), docker-proxy runs with `-use-listen-fd` flag. This causes:
- **TCP connections succeed** (port appears OPEN)
- **HTTP requests hang forever** (no response, timeout)

Diagnosis:
```bash
ps aux | grep docker-proxy | grep <port>  # look for "-use-listen-fd"
systemctl status docker.socket            # if active, this is the cause
```

Fix: `--network host` on the container (see Fix #1 below).

## Fix #1: `--network host` (PRIMARY — fixes docker-proxy + Tailscale in one shot)
```bash
docker stop <container> && docker rm <container>
docker run -d --name <container> --network host <other-flags> <image>
```
With `--network host`, nginx/services bind directly to host ports. No docker-proxy, no bridge networking, no `-use-listen-fd` hang. Ports are immediately reachable from Tailscale peers.

**Webtop example:**
```bash
docker run -d --name=webtop --network host \
  -e PUID=1000 -e PGID=1000 -e TZ=Asia/Bangkok \
  -e SUBFOLDERS=/ -e CUSTOM_PORT=3100 -e CUSTOM_HTTPS_PORT=3001 \
  -e TITLE="W.Alter Webtop" \
  -v /root/webtop/config:/config -v /root/webtop/Desktop:/config/Desktop \
  --shm-size=2g --restart unless-stopped \
  lscr.io/linuxserver/webtop:ubuntu-xfce
```

**Trade-off:** `--network host` means the container shares the host's network namespace — all container ports are directly on the host. No port isolation, but no docker-proxy bugs either.

## Fix #2: SSH Tunnel (secondary, for when `--network host` is not viable)
```bash
ssh -f -N -L <local-port>:127.0.0.1:<container-port> root@<vps-tailscale-ip>
```
Note: SSH tunnels DO work for plain HTTP services. The old belief that they "don't work for Selkies" was actually the docker-proxy hang masquerading as a tunnel problem.

## Fix #3: iptables rule (least reliable)
```bash
iptables -I INPUT -p tcp --dport <port> -j ACCEPT
```
Tailscale may regenerate `ts-input` on restart, overwriting this.

## Pitfalls
1. **docker-proxy `-use-listen-fd` hang**: The #1 cause of "port open but HTTP hangs". When `systemctl status docker.socket` shows active, docker-proxy uses systemd socket activation. TCP handshake succeeds, HTTP never responds. Fix: `--network host`.
2. **SSH tunnels actually work**: Old advice said "SSH tunnels don't work for Selkies/noVNC". That was wrong — the real problem was docker-proxy hanging (see #1). With `--network host` or a healthy docker-proxy, SSH tunnels work fine for WebSocket services too.
3. **Tailscale Funnel/Serve**: Works for exposing ports to the tailnet/internet, but only if the underlying port actually responds (i.e., docker-proxy is healthy or `--network host` is used). `tailscale serve --bg --https=443 http://localhost:<port>` for tailnet-only, `tailscale funnel` for public.
4. **Tunnel persistence**: SSH tunnels die when connection drops. Use `autossh -M 0 -f -N -L ...` for auto-reconnect, or use Tailscale Serve/Funnel instead.
5. **Multiple ports**: Webtop needs both 3001 (Selkies HTTPS) and 3100 (noVNC HTTP). With `--network host`, both bind directly. With SSH tunnels, create separate tunnels.
6. **Container restart resets networking**: If you `docker restart` a container that was created with bridge networking, it stays bridge. Must `docker rm` + `docker run --network host` to switch.
