# Camoufox MAX — systemd supervision and real health

## Why the service must be the owner

The MAX server listens on port 9377. Running a manually launched `server-max.js`
next to the systemd unit creates an ambiguous owner: an old process can retain
the port, use the wrong `HOME`, and make a later health check report the wrong
runtime. Keep one owner: `camoufox-max.service`.

## Required unit properties

The unit should:

- set `HOME=/root/.camoufox-node-home` so Node's Camoufox cache is isolated from
  Python's `~/.cache/camoufox`;
- set `CAMOFOX_MAX_PORT=9377` and `CAMOFOX_DATA_DIR=/root/.camoufox-max-data`;
- use `ExecStartPre` to fail early when the isolated `camoufox-bin` is absent;
- use `Restart=always` with `RestartSec` and `StartLimit*` bounds;
- use `TimeoutStartSec`, `TimeoutStopSec`, and `KillMode=mixed` for clean process
  ownership;
- remain enabled so it returns after reboot.

After installing or changing the unit:

```bash
systemctl daemon-reload
systemctl enable --now camoufox-max.service
```

Do not use a second `nohup`, `tmux`, or manually launched Node process on port
9377 in production.

## Eager browser boot and serialized launch

A Node HTTP listener can remain alive after the browser has died. `server-max.js`
should therefore call `ensureBrowser()` immediately after `app.listen()`. If the
launch fails, close the listener and exit non-zero so systemd can restart the
service instead of leaving a false-positive HTTP endpoint.

Guard `ensureBrowser()` with a shared in-flight promise. Concurrent requests
must await the same launch rather than starting multiple Camoufox processes:

```js
let browser = null;
let browserStartPromise = null;

async function ensureBrowser() {
  if (browser) return browser;
  if (browserStartPromise) return browserStartPromise;
  browserStartPromise = (async () => {
    browser = await firefox.launch(await launchOptions({
      headless: true,
      persistent_context: true,
      data_dir: CONTEXT_DIR,
    }));
    return browser;
  })();
  try {
    return await browserStartPromise;
  } finally {
    browserStartPromise = null;
  }
}
```

## Health contract

`/health` must check the browser connection, not merely `browser !== null`.
Use `browser.contexts()` or another low-cost protocol operation inside
`isBrowserAlive()`. Return `ok=false` and `browserConnected=false` when the
connection is dead. Keep metadata such as `running`, `flavor`, `sessions`, and
`persistent_context` for diagnostics.

The authoritative smoke test is stronger than `/health` alone:

1. `GET /health`: require HTTP 200, `ok=true`, and `browserConnected=true`.
2. Create a real tab through the compatibility route used by Hermes (`POST
   /tabs`, with `userId`, `sessionKey`, and a public URL).
3. Require a returned `tabId`.
4. Obtain a snapshot and require a non-empty semantic result.
5. Close the tab in cleanup.

This catches the important state where `/health` responds but
`browserContext.newPage()` fails with `Target page, context or browser has been
closed`.

## Verification after a repair

```bash
bash -n /root/.hermes/scripts/start-camoufox-max.sh
node --check /root/.hermes/camoufox-max/server-max.js
systemctl status camoufox-max.service --no-pager -l
systemctl is-active camoufox-max.service
systemctl is-enabled camoufox-max.service
curl -sS http://127.0.0.1:9377/health
```

Then run the tab → snapshot lifecycle, not just curl. Inspect `NRestarts`,
`ExecMainStatus`, the effective `HOME`, and the Camoufox child path in the
service cgroup. Ignore unrelated site-level console errors unless they prevent
tab creation or extraction.

## Operational lessons

- A SIGTERM from a stale/manual supervisor is not evidence of a Camoufox browser
  crash; inspect `systemctl status`, `ExecMainStatus`, and service ownership first.
- A systemd unit that still shows the old configuration needs `systemctl
  daemon-reload`; the warning is actionable, not cosmetic.
- An unavailable optional Camoufox backend should be reported separately from a
  healthy Walter Browse router. Do not label the entire web stack broken.
