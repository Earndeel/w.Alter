# cmux-notify end-of-run notifications for Hermes TUI

Use this when macOS cmux notifications work from app settings, but no notification arrives from a remote SSH/tmux Hermes TUI session. Do **not** rely on terminal bell/BEL (`\x07`) for this path; use `/usr/local/bin/cmux-notify`.

## Key architecture

`/usr/local/bin/cmux-notify` writes an OSC 777 notification sequence to stdout. In `hermes --tui`, the Python `tui_gateway` stdout is the JSON-RPC pipe, not the user's terminal. Therefore:

- Backend Python should **not** execute `cmux-notify` directly with stdout redirected to `/dev/null`.
- Backend Python should emit an internal TUI event, e.g. `cmux.notify` with `{success: true|false}`.
- Frontend Ink/Node TUI should execute `/usr/local/bin/cmux-notify` with `stdio: ['ignore', 'inherit', 'ignore']`, so stdout reaches the real cmux terminal.

## Event mapping

**Only trigger cmux.notify on events that mean "agent is now waiting for user input":**

- `message.complete` status `complete` → success
- `message.complete` status `error`/`failed`/`failure` → failure
- `error` event → failure
- `background.complete` text starting with `error:` → failure, otherwise success

**DO NOT trigger on these (causes notification spam on every tool/subagent call):**
- ~~tool completion~~ — remove `_emit_cmux_notify(sid, success=not bool(tool_error))` from tool completion handler
- ~~`subagent.complete`~~ — remove `_emit_cmux_notify(...)` from subagent completion handler

The user only wants a notification when the run is fully done and the agent is idle waiting for interaction — not during the run.

## Frontend helper

In `ui-tui/src/app/createGatewayEventHandler.ts`, add a small helper:

```ts
import { spawn } from 'node:child_process'

const CMUX_NOTIFY_BIN = '/usr/local/bin/cmux-notify'

const notifyCmux = (success: boolean) => {
  const title = success ? 'Hermes ✅' : 'Hermes ❌'
  const body = success ? 'Run terminée' : 'Run échouée'
  try {
    const child = spawn(CMUX_NOTIFY_BIN, [title, body], {
      stdio: ['ignore', 'inherit', 'ignore']
    })
    child.on('error', () => {})
    child.unref()
  } catch {
    // Optional integration; never break TUI event loop.
  }
}
```

Handle event:

```ts
case 'cmux.notify':
  notifyCmux(Boolean(ev.payload.success))
  return
```

Add to `ui-tui/src/gatewayTypes.ts`:

```ts
| { payload: { success?: boolean }; session_id?: string; type: 'cmux.notify' }
```

## Backend pattern

In `tui_gateway/server.py`, keep normal event emission first, then emit a second internal `cmux.notify` JSON-RPC event. Avoid recursion by writing `cmux.notify` directly with `write_json`, not via `_emit()`.

Pseudo-pattern:

```py
def _emit(event: str, sid: str, payload: dict | None = None):
    params = {"type": event, "session_id": sid}
    if payload is not None:
        params["payload"] = payload
    write_json({"jsonrpc": "2.0", "method": "event", "params": params})
    _cmux_notify_for_event(event, sid, payload)


def _emit_cmux_notify(sid: str, success: bool) -> None:
    if not sid:
        return
    write_json({
        "jsonrpc": "2.0",
        "method": "event",
        "params": {
            "type": "cmux.notify",
            "session_id": sid,
            "payload": {"success": bool(success)},
        },
    })
```

## Pitfall: no tmux client attached (direct SSH users)

When the user connects via **direct SSH** (not attached to the server-side tmux session where Hermes TUI runs), `cmux-notify` escape sequences get trapped inside tmux with no client to relay them to cmux on the Mac. Enabling `allow-passthrough` is NOT enough — there must be a tmux client attached for passthrough to work.

**Detection:** `tmux list-clients` returns empty even though the user is actively chatting.

**Fix:** Modify `/usr/local/bin/cmux-notify` to also write directly to SSH ttys as a fallback:

```bash
#!/usr/bin/env bash
title="${1:-Hermes}"
body="${2:-Terminé}"

# Get our own pts to skip (may fail if stdin is 'ignore' from Node spawn)
SELF_PTS=$(basename "$(tty 2>/dev/null)" 2>/dev/null)

# Also get the parent process pts to skip
PARENT_PTS=$(ps -o tty= -p "$PPID" 2>/dev/null | tr -d ' ')

# Always try tmux passthrough (no-op if not in tmux)
printf '\033Ptmux;\033\033]777;notify;%s;%s\007\033\\' "$title" "$body" 2>/dev/null

# Always try direct OSC (works if we're not in tmux)
printf '\033]777;notify;%s;%s\007' "$title" "$body" 2>/dev/null

# Always try writing to SSH bash ttys (critical fallback for direct SSH users)
for pts in /dev/pts/[0-9]*; do
  num=$(basename "$pts")
  [ "$num" = "$SELF_PTS" ] && continue
  [ "$num" = "$PARENT_PTS" ] && continue
  [ "$num" = "0" ] && continue  # pts/0 = hermes TUI tmux pane — skip
  cmd=$(ps -t "pts/$num" -o comm= 2>/dev/null | head -1)
  if [ "$cmd" = "bash" ] && [ -w "$pts" ]; then
    printf '\033]777;notify;%s;%s\007' "$title" "$body" > "$pts" 2>/dev/null
  fi
done
```

**Why no `$TMUX` detection:** Node's `spawn` with `stdio: ['ignore', 'inherit', 'ignore']` does NOT reliably inherit the `TMUX` environment variable — observed as `TMUX=unset` in the child even though the parent Node process has it set at `/proc/<pid>/environ`. Always try all methods unconditionally.

**Why skip pts/0:** The Hermes TUI tmux pane is always `/dev/pts/0`. Writing to it is pointless (no one reads it) and `tty` returns "not a tty" when stdin is `'ignore'`, so `SELF_PTS` detection fails. Hard-skip `pts/0`.

**Why bash filter:** SSH sessions run `bash`; tmux panes show `bash` too but the `pts/0` skip handles the hermes pane. The `pts` check + `comm=bash` targets SSH shells specifically.

## Verification

- Disable old bell config: `hermes config set display.bell_on_complete false`
- Rebuild bundle: `npm --prefix ui-tui run build`
- Verify no old run-complete bell call remains: search `ui-tui/dist/entry.js` for `stdout.write("\\x07")`.
- Verify backend syntax: `python3 -m py_compile tui_gateway/server.py`
- Mock backend `write_json` and assert `cmux.notify` frames are generated for success/failure paths.
- **New:** Test the SSH fallback — from agent's `terminal()`, run `/usr/local/bin/cmux-notify "Hermes ✅" "Test"`. User should see notification on their cmux even when no tmux client is attached.
- **Debug logging:** Add `echo "$(date) called title=$title body=$body" >> /tmp/cmux-notify.log` to the top of the script to verify it's being called. Check `cat /tmp/cmux-notify.log` after a run to see which ttys were written to. This was essential to discover the `$TMUX` inheritance issue.

## Persistence across updates

### `allow-passthrough` must be ON in server-side tmux

The #1 reason cmux-notify silently fails: the server-side tmux session (where Hermes `--tui` runs) has `allow-passthrough off` by default. The OSC 777 escape sequence gets swallowed by tmux and never reaches the SSH tunnel → cmux client.

```bash
# Check
tmux show-option -g allow-passthrough

# Fix (runtime + persistent)
tmux set -g allow-passthrough on
grep -q "allow-passthrough" ~/.tmux.conf || echo 'set -g allow-passthrough on' >> ~/.tmux.conf
```

This is easy to miss because `cmux-notify` called from a bare SSH shell (outside tmux) works fine — the passthrough is only needed when the escape sequence originates **inside** a tmux pane (i.e., from the Hermes TUI frontend Node process).

### `bell_on_complete` must be OFF

The cmux-notify path replaces the BEL (`\x07`) path. If both are active, you may get double notifications or interference. Set `display.bell_on_complete: false` in config.yaml.

## Persistence across updates

If local TUI overrides are restored after `hermes update`, copy patched frontend files into `~/.hermes/tui-overrides/` and have the restore script copy them back before rebuilding. Keep backend injection in an idempotent script, e.g. `~/.hermes/scripts/apply-cmux-notify-patch.py`, called by `restore-tui-design.sh`.
