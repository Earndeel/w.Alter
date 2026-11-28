# SSH Hardening: Mac ↔ VPS via Tailscale

## authorized_keys restrictions

Both sides restrict keys to each other's Tailscale IP only.

### Mac `~/.ssh/authorized_keys`
```
from="100.91.35.121",no-agent-forwarding,no-x11-forwarding ssh-ed25519 <VPS_PUBKEY> root@w-alter
```

### VPS `~/.ssh/authorized_keys`
```
from="100.127.150.1",no-agent-forwarding,no-x11-forwarding ssh-ed25519 <MAC_PUBKEY> lucasjouvencon@Lucass-MacBook-Pro-15.local
```

- `from=` — key only accepted from this IP (Tailscale). Any other source = rejected.
- `no-agent-forwarding` — prevents SSH agent forwarding through this key
- `no-x11-forwarding` — prevents X11 tunneling
- Do NOT use `restrict` — it blocks PTY allocation needed for shell access

## sshd hardening

### VPS: `/etc/ssh/sshd_config.d/99-walter-hardening.conf`
```
PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers root ubuntu
```
Then: `systemctl reload sshd`

### Mac: `/etc/ssh/sshd_config.d/99-walter-hardening.conf` (requires sudo)
```
PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers lucasjouvencon
```
Then: `sudo launchctl kickstart -k system/com.openssh.sshd`

**Note**: On macOS, sshd config changes require sudo. The system blocks piping passwords to `sudo -S` over SSH. Two approaches:
1. **Send via Telegram** for Lucas to run locally (preferred — paste the commands, he types sudo password himself)
2. **Mac password in vault**: `vault get macos/lucas_password` — stored for reference but cannot be piped to sudo remotely due to the blocking policy.

## Tailscale ACLs

Restrict SSH to only Mac ↔ VPS in Tailscale admin (https://login.tailscale.com/admin/acls):

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["100.127.150.1", "100.91.35.121"],
      "dst": ["100.127.150.1:22", "100.91.35.121:22"]
    }
  ]
}
```

Without this, any device on the Tailscale network can SSH to either machine.

## Backup SSH Key (disaster recovery)

If Lucas loses his Mac or phone, he needs a way to access the VPS from any device.

### Setup
1. Generate a passphrase-protected key:
   ```bash
   ssh-keygen -t ed25519 -f /tmp/ssh-backup-key -C "backup@w-alter" -N "{{bw:W.Alter · ssh:field:backup_passphrase}}"
   ```

2. Add public key to VPS `~/.ssh/authorized_keys` (NO `from=` restriction — accessible from any IP):
   ```
   ssh-ed25519 <BACKUP_PUBKEY> backup@w-alter
   ```

3. Store private key + passphrase in vault:
   ```bash
   vault add ssh backup_private_key "$(cat /tmp/ssh-backup-key)"
   vault add ssh backup_passphrase "{{bw:W.Alter · ssh:field:backup_passphrase}}"
   ```

4. Store in Bitwarden as secure note "W.Alter SSH Backup Key" with instructions.

5. Clean up temp files: `rm -f /tmp/ssh-backup-key /tmp/ssh-backup-key.pub`

### Recovery procedure (from any device)
1. Log into Bitwarden
2. Get the backup private key from "W.Alter SSH Backup Key" note
3. Save as `~/.ssh/id_ed25519_backup`, chmod 600
4. Install Tailscale, join the tailnet
5. `ssh -i ~/.ssh/id_ed25519_backup root@100.91.35.121`

## Verification

1. From VPS: `ssh lucasjouvencon@100.127.150.1 "echo OK"` — should work
2. From Mac: `ssh root@100.91.35.121 "echo OK"` — should work
3. From another Tailscale device: SSH to either — should be REJECTED
4. Password auth test: `ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no user@host` — should be REJECTED
