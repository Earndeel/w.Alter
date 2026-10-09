# Oracle Cloud + Tailscale Exit Node — SIP Routing Fix

## Problem

Oracle Cloud VPS (10.0.0.24 → public 129.150.52.60) with Tailscale. Mac advertised as exit node (`ExitNode=True, AllowedIPs=['0.0.0.0/0']`). Tailscale routing rule 5270 (`from all lookup 52`) sends ALL traffic through tailscale0, including SIP to linphone.org (176.31.149.179).

Result: SIP registration goes through Mac's public IP (124.120.206.170), not VPS (129.150.52.60). SDP/Via headers show wrong IP. Audio routing breaks.

## Diagnosis

```bash
# Check which route SIP traffic takes
ip route get 176.31.149.179
# Bad: "dev tailscale0 table 52 src 100.91.35.121"
# Good: "via 10.0.0.1 dev enp0s6 src 10.0.0.24"

# Check Tailscale exit node config
tailscale debug prefs | grep ExitNode
tailscale status --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['Self'].get('ExitNode'), d['Self'].get('ExitNodeID'))"

# Check Asterisk registration
asterisk -rx "pjsip show registrations"
# "Rejected" or "Unregistered" = routing problem
```

## Fix

### 1. Clear Tailscale exit node preference

```bash
tailscale set --exit-node=
```

### 2. Add explicit route for linphone.org via VPS gateway

```bash
ip route add 176.31.149.179/32 via 10.0.0.1 dev enp0s6 table 52
```

### 3. Create transport-public bound to VPS interface

In `/etc/asterisk/pjsip.conf`:

```ini
[transport-public]
type=transport
protocol=udp
bind=10.0.0.24:5060
external_media_address=129.150.52.60
external_signaling_address=129.150.52.60
```

Use `transport=transport-public` for the linphone.org trunk, NOT `transport-tailscale`.

### 4. Fix identify match

```ini
; WRONG — causes getaddrinfo error
match=sip:sip.linphone.org

; CORRECT
match=176.31.149.179
```

### 5. Open firewall

```bash
iptables -I INPUT 3 -p udp --dport 5060 -j ACCEPT
iptables -I INPUT 4 -p udp --dport 10000:20000 -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```

### 6. Persist across reboots

**Route** in `/etc/rc.local`:
```bash
ip route add 176.31.149.179/32 via 10.0.0.1 dev enp0s6 table 52 2>/dev/null || true
```

**iptables** via systemd service `/etc/systemd/system/iptables-restore.service`:
```ini
[Unit]
Description=Restore iptables rules
Before=asterisk.service

[Service]
Type=oneshot
ExecStart=/sbin/iptables-restore /etc/iptables/rules.v4
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

### 7. Restart and verify

```bash
systemctl restart asterisk
sleep 5
asterisk -rx "pjsip send register linphone-walter-registration"
sleep 10
asterisk -rx "pjsip show registrations"
# Should show "Registered (exp. XXXs)"
```

## Oracle Security List (separate from iptables)

Oracle Cloud has a SECOND firewall at the VCN/subnet level (Security List). iptables only controls the VM. If registration works but incoming calls don't arrive (no INVITE in `full.log`), open UDP 5060 + 10000-20000 in the Oracle Console → Networking → Virtual Cloud Networks → Security Lists.

Requires OCI console access or `oci` CLI (not installed on this VM).

## Verification Commands

```bash
# Route check
ip route get 176.31.149.179

# Transport check
asterisk -rx "pjsip show transports"

# Registration check
asterisk -rx "pjsip show registrations"

# SIP traffic verification (Via header should show public IP)
tail -f /var/log/asterisk/full.log | grep "Via:"

# Bridge health
curl http://127.0.0.1:12100/health
```
