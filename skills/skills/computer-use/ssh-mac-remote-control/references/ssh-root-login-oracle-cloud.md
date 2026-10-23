# SSH Root Login on Oracle Cloud VPS

Oracle Cloud Ubuntu instances block root SSH login via a forced command in `authorized_keys`.

## The Problem

`/root/.ssh/authorized_keys` contains:
```
no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="echo 'Please login as the user \"ubuntu\" rather than the user \"root\".';echo;sleep 10;exit 142" ssh-rsa AAAA... ssh-key-2025-12-10
```

This rejects root login even with valid key auth. The `sshd_config.d/` also has:
```
AllowUsers root ubuntu
PasswordAuthentication no
```

## The Fix

1. Remove the forced-command entry from `/root/.ssh/authorized_keys`:
   ```bash
   grep -v "Please login as" /root/.ssh/authorized_keys > /tmp/ak_clean
   mv /tmp/ak_clean /root/.ssh/authorized_keys
   chmod 600 /root/.ssh/authorized_keys
   ```

2. Add the Mac's public key without forced command (or it's already there from the duplicate entry added earlier).

3. Verify from Mac:
   ```bash
   ssh -o StrictHostKeyChecking=accept-new -i ~/Desktop/Keys/ssh-key-2025-12-10.key -p 2222 root@localhost 'echo ROOT_OK'
   ```

## Why Root is Needed

Hermes Desktop app reads `~/.hermes/` on the remote. Hermes runs as root, so `/root/.hermes/` is mode 700. The `ubuntu` user cannot access it even with:
- ACLs (`setfacl`) — mask resets by Hermes
- Group permissions (`chmod g+rX`) — Hermes resets to 700
- Symlinks — resolve through target permissions
- Bind mounts — makes source read-only

Root SSH login is the only reliable solution.

## Pitfall: ubuntu in root group

The `ubuntu` user is in gid 0 (root group). This means:
- `chmod 705` (rwx---r-x) FAILS — kernel checks group (`---`) before other (`r-x`)
- `chmod 755` (rwxr-xr-x) WORKS — group has `r-x`

Always use `chmod 755` when ubuntu is in root group.
