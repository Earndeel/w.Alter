# Brave walter Relaunch

The brave-walter instance can crash or die unexpectedly (e.g., when Playwright CDP connection drops). To relaunch:

```bash
ssh -o ConnectTimeout=8 -i ~/.ssh/id_ed25519 lucasjouvencon@100.127.150.1 '
# Kill stale processes and clean lock
pkill -f "user-data-dir=/tmp/brave-walter" 2>/dev/null
rm -f /tmp/brave-walter/SingletonLock
sleep 1

# Launch with full path (open -a may open tab in main Brave instead)
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  --user-data-dir=/tmp/brave-walter \
  --remote-debugging-port=9226 \
  --no-first-run --disable-default-apps --no-default-browser-check \
  "about:blank" &>/dev/null &
disown
'
```

**Pitfall**: `open -a "Brave Browser" --args ...` does NOT reliably start a new instance — it may open a tab in the existing main Brave instead. Always use the full binary path.

After launch, wait 5-8 seconds, then verify:
```bash
ssh lucasjouvencon@100.127.150.1 'curl -s http://localhost:9226/json/version | head -3'
```

Re-establish SSH tunnel:
```bash
pkill -f "ssh.*9226.*100.127.150.1" 2>/dev/null
ssh -f -N -L 9226:localhost:9226 lucasjouvencon@100.127.150.1
```

## Downloads via CDP

When downloading files via Playwright CDP connected to brave-walter, `download.save_as()` saves on the VPS (empty files). The actual download goes to the Mac. **Workaround**: intercept the download URL via `page.expect_download()`, then use `curl` to download to VPS:

```python
with page.expect_download(timeout=15000) as dl_info:
    page.click('button:has-text("Download")')
dl = dl_info.value
# dl.url is the S3/CDN direct download URL
# Use curl on VPS to download it
```
