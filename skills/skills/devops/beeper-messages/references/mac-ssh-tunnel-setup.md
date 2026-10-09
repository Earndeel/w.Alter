# Mac SSH Tunnel Setup (Permanent + Auto-Recover)

The autossh reverse tunnel from Mac to VPS dies when the Mac sleeps. This LaunchAgent makes it permanent.

## Prerequisites

1. VPS SSH key must be in Mac's `~/.ssh/authorized_keys`:
   ```bash
   echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBnKADFi1tBAVJzyKiSVRGHdPM+QOFH6Gn5sWwrnjgfa root@w-alter' >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

2. autossh installed: `brew install autossh`

## LaunchAgent (run once on Mac)

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.walter.ssh-tunnel.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.walter.ssh-tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/autossh</string>
        <string>-M</string><string>0</string>
        <string>-N</string><string>-T</string>
        <string>-o</string><string>ServerAliveInterval=30</string>
        <string>-o</string><string>ServerAliveCountMax=3</string>
        <string>-o</string><string>ExitOnForwardFailure=yes</string>
        <string>-R</string><string>2222:localhost:22</string>
        <string>root@100.91.35.121</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardErrorPath</key><string>/tmp/walter-tunnel.err</string>
    <key>StandardOutPath</key><string>/tmp/walter-tunnel.out</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AUTOSSH_GATETIME</key><string>0</string>
        <key>AUTOSSH_POLL</key><string>30</string>
    </dict>
</dict>
</plist>
PLIST

pkill -f "autossh.*2222" 2>/dev/null; sleep 1
launchctl unload ~/Library/LaunchAgents/com.walter.ssh-tunnel.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.walter.ssh-tunnel.plist
```

## VPS SSH Config

```bash
cat > ~/.ssh/config << 'EOF'
Host mac
    HostName localhost
    Port 2222
    User lucasjouvencon
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking no
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ConnectTimeout 5
    Compression yes
EOF
chmod 600 ~/.ssh/config
```

## Verification

From VPS: `ssh mac 'echo connected'`
Tunnel health: `ssh mac 'cat /tmp/walter-tunnel.err | tail -5'`

## What this provides

- **Permanent**: starts at boot via LaunchAgent
- **Auto-reconnect**: `KeepAlive` + `AUTOSSH_POLL=30` — reconnects every 30s if dropped
- **Sleep-resistant**: `ServerAliveInterval=30` detects dead connections
- **Secure**: ed25519 key auth, no passwords
