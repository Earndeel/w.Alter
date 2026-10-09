# Outbound Calls via Linphone.org + Oracle Cloud SIP Routing

## Problem: VPS behind Tailscale exit node

The VPS (Oracle Cloud, private IP `10.0.0.24`) uses Tailscale. The Mac advertises exit node, so by default ALL traffic routes through the Mac's public IP (`124.120.206.170`), not the VPS's own IP (`129.150.52.60`). This breaks SIP because:
- linphone.org sees the Mac's IP, not the VPS IP
- `external_media_address` in pjsip.conf would be wrong
- RTP media would route through the Mac (fragile, latency)

### Fix applied
1. **Disabled Tailscale exit node**: `tailscale set --exit-node=` (clears the preference)
2. **Route linphone.org directly**: `ip route add 176.31.149.179/32 via 10.0.0.1 dev enp0s6 table 52` (bypasses Tailscale for SIP traffic)
3. **Persisted in `/etc/rc.local`**

### Transport config
Created `transport-public` bound to `10.0.0.24:5060` (Oracle private IP, routes through Oracle NAT → public IP `129.150.52.60`):
```ini
[transport-public]
type=transport
protocol=udp
bind=10.0.0.24:5060
external_media_address=129.150.52.60
external_signaling_address=129.150.52.60
```

The linphone.org trunk and earndeel endpoint both use `transport=transport-public`.

### Firewall
```bash
iptables -I INPUT 3 -p udp --dport 5060 -j ACCEPT
iptables -I INPUT 4 -p udp --dport 10000:20000 -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```
Persisted via `iptables-restore.service` systemd unit.

## Outbound calls to earndeel (iPhone)

### Endpoint config for calling through linphone.org trunk
To call `earndeel@sip.linphone.org` from Asterisk, need a dedicated PJSIP endpoint:
```ini
[earndeel-auth]
type=auth
auth_type=userpass
username=earndeel
password=<THE_PASSWORD>

[earndeel-aor]
type=aor
contact=sip:earndeel@sip.linphone.org
qualify_frequency=0

[earndeel]
type=endpoint
transport=transport-public
context=from-linphone-walter
disallow=all
allow=opus,ulaw
aors=earndeel-aor
outbound_auth=linphone-walter-auth  ; use w.alter.ai auth for outbound
from_user=w.alter.ai
from_domain=sip.linphone.org
rewrite_contact=yes
rtp_symmetric=yes
force_rport=yes
direct_media=no
language=fr
```

**Critical**: `outbound_auth=linphone-walter-auth` — the INVITE must be authenticated with the registered trunk's credentials (w.alter.ai), NOT the target user's credentials. linphone.org proxies the call; Asterisk authenticates as w.alter.ai.

### AMI Originate for outbound call
```python
import socket, time
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.settimeout(10)
tcp.connect(("127.0.0.1", 5038))
tcp.sendall(b"Action: Login\r\nUsername: hermes-ami\r\nSecret: hermesami2026\r\nEvents: off\r\n\r\n")
time.sleep(1)
tcp.recv(4096)
tcp.sendall(
    b"Action: Originate\r\n"
    b"Channel: PJSIP/earndeel\r\n"
    b"Context: from-linphone-walter\r\n"
    b"Exten: 200\r\n"
    b"Priority: 1\r\n"
    b"CallerID: W.Alter <w.alter.ai>\r\n"
    b"Timeout: 30000\r\n"
    b"Async: yes\r\n"
    b"\r\n"
)
```

**Pitfall**: Do NOT use `Channel: PJSIP/earndeel@sip.linphone.org` — that tries to find an endpoint named `sip.linphone.org` and fails with "endpoint not found". Use `PJSIP/earndeel` (the endpoint name).

### Call flow
1. Asterisk sends INVITE to `earndeel@sip.linphone.org` via transport-public
2. linphone.org authenticates the INVITE (as w.alter.ai)
3. linphone.org looks up earndeel's registration (from iPhone's Linphone app)
4. linphone.org sends push notification to iPhone (110 Push sent)
5. iPhone wakes up and responds to the INVITE
6. If accepted: RTP media flows VPS ↔ iPhone (via linphone.org proxy)

### SIP response codes seen
- **100 Trying**: linphone.org received the INVITE
- **110 Push sent**: push notification sent to iPhone (app in background)
- **488 Not acceptable here**: Linphone iOS rejects the SDP (likely SRTP requirement — see below)
- **403 Forbidden**: earndeel registration from Asterisk fails (wrong password or account restriction)
- **200 OK**: registration successful (w.alter.ai)

## Known issue: 488 Not acceptable here (Linphone iOS)

Linphone iOS 6.0.3 rejects INVITEs with `488 Not acceptable here`. The SDP looks correct (opus, PCMU, PCMA on public IP 129.150.52.60). Most likely cause:

**Linphone iOS defaults to SRTP (media encryption) but Asterisk sends plain RTP.**

### Workarounds (pending verification)
1. **iPhone side**: Linphone settings → Media encryption → set to "None" / "Disabled"
2. **Asterisk side**: Enable SRTP on the earndeel endpoint (`media_encryption=sdes`) — requires `res_srtp` module
3. **First call worked, subsequent calls 488**: The first call (missed) may have succeeded because the app was in foreground with different media settings. Background calls via push may enforce stricter policies.

## pjsip.conf identify pitfall

The `match=` field in `[*-identify]` sections must be an IP address or hostname, NOT a SIP URI:
```ini
# WRONG — causes "getaddrinfo('sip', 'sip.linphone.org', ...)" error
match=sip:sip.linphone.org

# CORRECT
match=176.31.149.179
```
