# SIP 482 Loop Detected — same-provider outbound calls (2026-05-23)

## Problem
When both From (w.alter.ai) and To (earndeel) are on the same SIP domain (sip.linphone.org), the Flexisip proxy returns `482 Loop Detected` even with valid Proxy-Auth credentials.

## Reproduction
```python
# Send raw INVITE to sip.linphone.org proxy
# From: w.alter.ai@sip.linphone.org
# To: earndeel@sip.linphone.org
# Step 1: 407 Proxy Auth Required (expected)
# Step 2: Re-send with Proxy-Auth digest → 482 Loop Detected
```

## Root cause
The INVITE comes from outside the proxy's registration context (raw UDP from VPS, not through an established registration channel). Flexisip's routing logic detects the From/To as an intra-domain loop because both users share the same SIP domain.

## What works
Asterisk PJSIP/earndeel with `outbound_auth=linphone-walter-auth` succeeds (180 Ringing → 200 OK). Asterisk has its own registration to sip.linphone.org and uses proper Route headers that the proxy trusts.

## SIP digest auth details
- Auth header parsing: must strip "Digest " prefix before splitting params
- Initial parser bug: `split(",", 1)[0]` only reads first param (realm), loses nonce/qop/opaque
- Fix: split all params individually: `for part in params_str.split(",")`
- qop=auth requires nc + cnonce in the response hash
- Correct password for w.alter.ai@sip.linphone.org: `{{bw:9a13ec17-b3c5-4278-a6bc-a5e8517a5187:password}}`
- Asterisk's pjsip.conf uses `h3rm3s_2026_s1p` (different password, same account — may have been changed)

## Verified test
```python
import socket, uuid, hashlib
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5)
sock.bind(('0.0.0.0', 0))
# 1. Send INVITE → 407 with Proxy-Authenticate header
# 2. Parse nonce, realm, qop from Proxy-Authenticate
# 3. Calculate HA1=md5(user:realm:pass), HA2=md5("INVITE:uri")
# 4. response=md5(HA1:nonce:nc:cnonce:qop:HA2) when qop=auth
# 5. Re-send with Proxy-Authorization header → 482 Loop Detected
```

## Lesson
For intra-domain calls on sip.linphone.org, always route through Asterisk AMI, not raw SIP.
