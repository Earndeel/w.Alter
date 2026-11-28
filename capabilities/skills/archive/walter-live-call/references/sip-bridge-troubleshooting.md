# SIP Bridge Troubleshooting — Call Connected But No Audio

## Quick diagnosis flow

```
Call arrives → Channel Up but no voice?
│
├─ Bridge logs show "Answer failed: 401"?
│  → ARI Basic Auth missing on REST calls
│  → Fix: ClientSession(auth=BasicAuth(ARI_USER, ARI_PASS))
│
├─ Bridge logs show "Address already in use"?
│  → ExternalMedia duplication loop OR stale RTP sockets
│  → Fix: filter StasisStart for UnicastRTP/ExternalMedia + SO_REUSEADDR
│
├─ Bridge logs show "ExternalMedia failed"?
│  → Check RTP port range not exhausted (12000-12020 = 11 sessions max)
│  → `asterisk -rx "core show channels"` — count UnicastRTP channels
│  → `asterisk -rx "channel request hangup all"` to clean up
│
├─ SIP 488 "Not acceptable here"?
│  → Linphone iOS requires SRTP or user must disable media encryption
│  → Check: does the 488 response include SDP? No = client-side rejection
│
├─ SIP INVITE sent but no response?
│  → Oracle Security List blocking inbound UDP
│  → iptables open but cloud-level rules still block
│  → Test: `tcpdump -i enp0s6 -n udp port 5060 -c 5` while calling
│
└─ Registration OK but INVITE times out?
   → Wrong transport: using tailscale when public IP needed
   → Check: `ip route get 176.31.149.179` must go via enp0s6, not tailscale0
```

## Common fixes

### Clean up leaked channels
```bash
asterisk -rx "core show channels" | grep UnicastRTP | wc -l
# If > 1, you have leaked channels
asterisk -rx "channel request hangup all"
systemctl restart hermes-bridge
```

### Verify ARI auth works
```bash
curl -s -u hermes:hermesari2026 http://127.0.0.1:8088/ari/asterisk/info | python3 -c "import json,sys; print(json.load(sys.stdin).get('version','FAIL'))"
```

### Verify bridge can answer
```bash
journalctl -u hermes-bridge --since "30 sec ago" | grep -E "Answer|Error|failed|401"
```

### Check SIP registration
```bash
asterisk -rx "pjsip show registrations"
# Should show "Registered (exp. XXXs)"
# If "Rejected" or "Unregistered":
asterisk -rx "pjsip send register linphone-walter-registration"
sleep 10
asterisk -rx "pjsip show registrations"
```

### Force outbound call (test)
```python
import socket, time
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.settimeout(10)
tcp.connect(("127.0.0.1", 5038))
tcp.sendall(b"Action: Login\r\nUsername: hermes-ami\r\nSecret: hermesami2026\r\nEvents: off\r\n\r\n")
time.sleep(1); tcp.recv(4096)
tcp.sendall(b"Action: Originate\r\nChannel: PJSIP/earndeel\r\nContext: from-linphone-walter\r\nExten: 200\r\nPriority: 1\r\nCallerID: W.Alter <w.alter.ai>\r\nTimeout: 30000\r\nAsync: yes\r\n\r\n")
time.sleep(3); print(tcp.recv(4096).decode().split('\n')[0])
tcp.sendall(b"Action: Logoff\r\n\r\n"); time.sleep(1); tcp.close()
```

## Endpoint config for outbound calls to earndeel

```ini
[earndeel-auth]
type=auth
auth_type=userpass
username=earndeel
password=<from-vault>

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
outbound_auth=linphone-walter-auth   ; use REGISTERED trunk auth, not target user's
from_user=w.alter.ai
from_domain=sip.linphone.org
rewrite_contact=yes
rtp_symmetric=yes
force_rport=yes
direct_media=no
language=fr
```

Key: `outbound_auth` must use the trunk credentials (`linphone-walter-auth`), NOT the target user's auth. linphone.org routes based on the From/Proxy-Authorization, not the To field.

## Linphone iOS setup

1. Account: `earndeel@sip.linphone.org`
2. Password: stored in Bitwarden
3. Transport: UDP
4. **Media encryption: None** (SRTP causes 488 rejections with plain-RTP Asterisk)
5. Call: dial `200` for W.Alter, `999` for echo test
