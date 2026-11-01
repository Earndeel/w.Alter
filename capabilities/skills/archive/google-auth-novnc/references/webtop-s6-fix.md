# Webtop s6 Service Fix

## Problem
Webtop container (Alpine + s6-overlay) fails to start with:
```
s6-rc: fatal: unable to read /etc/s6-overlay/s6-rc.d/svc-chromium/type: No such file or directory
```

The `svc-chromium` directory exists but is empty — missing `type`, `run`, and `dependencies.d/`.

## Fix
```bash
# Create type file
docker exec webtop bash -c 'echo "longrun" > /etc/s6-overlay/s6-rc.d/svc-chromium/type'

# Create run script (stub — actual Chromium is managed by webtop-chromium service)
docker exec webtop bash -c 'cat > /etc/s6-overlay/s6-rc.d/svc-chromium/run << "RUNEOF"
#!/command/execlineb -P
foreground { echo "svc-chromium: stub (managed by webtop-chromium)" }
/bin/sleep infinity
RUNEOF
chmod +x /etc/s6-overlay/s6-rc.d/svc-chromium/run'

# Create dependencies
docker exec webtop bash -c 'mkdir -p /etc/s6-overlay/s6-rc.d/svc-chromium/dependencies.d && touch /etc/s6-overlay/s6-rc.d/svc-chromium/dependencies.d/base'

# Restart container
docker restart webtop
```

## Verify
```bash
sleep 15
docker exec webtop ps aux | grep -E "selkies|nginx|xorg|dbus" | grep -v grep
curl -sk https://100.91.35.121:3001/ -o /dev/null -w "Selkies: %{http_code}\n"
```

## Notes
- The `svc-chromium` service is a stub — real Chromium is managed by `webtop-chromium` (separate s6 service).
- If other s6 services are broken, same pattern: create `type`, `run`, `dependencies.d/`.
- Selkies desktop runs on port 3001 (mapped to host via Docker).
