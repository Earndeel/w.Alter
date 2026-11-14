# Direct Mac Cua CLI fallback and Safari notes

## When to use

Use this only when the Hermes `computer_use` remote wrapper cannot start, but
there is an explicitly configured SSH/Tailscale route to the interactive Mac.
A wrapper refusal is a transport/integration problem, not proof that the Mac is
unreachable. Do not start a local Linux driver and call it Mac control.

## Read-only target-side sequence

Run from the Hermes host, substituting the configured Mac username, address,
and installed CLI path:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 \
  -i ~/.ssh/id_ed25519 <mac-user>@<mac-tailscale-ip> \
  'sw_vers; id -u; launchctl print gui/$(id -u) >/dev/null && echo GUI_LAUNCHD=ok'

ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 \
  <mac-user>@<mac-tailscale-ip> \
  '<home>/.local/bin/cua-driver status'

ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 \
  <mac-user>@<mac-tailscale-ip> \
  '<home>/.local/bin/cua-driver permissions status --json'

ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 \
  <mac-user>@<mac-tailscale-ip> \
  '<home>/.local/bin/cua-driver call health_report "{}"'
```

Require the signed CuaDriver daemon to be running, the target GUI session to
be available, Accessibility and Screen Recording to be granted, and
`health_report.overall` to be `ok`. The read-only permission booleans are a
hint; retain the capture/AX gate before any mutation.

Then discover the live window and read its current AX state:

```bash
cua-driver call list_windows '{"on_screen_only":false}'
cua-driver call get_window_state \
  '{"pid":<current-pid>,"window_id":<current-window-id>,"include_screenshot":true}'
```

Use the exact current `(pid, window_id)` pair returned by `list_windows`.
Element indices/tokens are scoped to the newest `get_window_state` snapshot.
If the read returns `ax_window_unresolved`, re-list windows and take a fresh
snapshot; do not act on elements from another Safari surface or from a stale
window record. If the resulting snapshot does not contain coherent pixels,
stop rather than guessing a coordinate transform.

## Safari-specific routing

Safari has no Chromium CDP route. For simple deterministic navigation, use
Safari AppleScript from the Mac session, then verify with a fresh Cua window
read or Safari AppleScript state read:

```bash
osascript <<'APPLESCRIPT'
tell application "Safari"
  activate
  if (count of windows) = 0 then
    make new document with properties {URL:"https://www.youtube.com"}
  else
    tell front window
      set URL of current tab to "https://www.youtube.com"
    end tell
  end if
end tell
APPLESCRIPT
```

For clicks, prefer a fresh Cua AX element action when the target is exposed.
Use pixel coordinates only when the same fresh scoped snapshot explicitly
provides a coherent screenshot and the action is within the approved Cua
interaction contract. Verify the destination URL/title after the click. A
loaded site is not evidence that the requested content exists: for example,
YouTube can show an empty personalized home with “Try searching to get
started”, in which case there is no first video to click and the correct action
is to ask what to search for.

## Safety and verification

- Never automatically replay an uncertain mutation through the legacy screen
  server or a second driver.
- Never automate permission, password, payment, or security prompts.
- Never infer success from `{ok:true}`, an HTTP 200, or a page title alone.
- After every mutation, obtain fresh state and verify the requested
  postcondition; if completion is unknown, inspect before retrying.
- Leave persistent CuaDriver and screen-server processes intact; close only
  temporary diagnostic sessions and remove only captures created by the test.
