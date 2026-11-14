# Foreground-control approval gate

Use this pattern when a Mac automation service can either observe the desktop or visibly control it.

## Contract

- `health` and `screenshot` are read-only and never prompt.
- Input endpoints default to **foreground** and must obtain a native approval lease before invoking `cliclick` or `osascript`.
- The prompt must state the reason and expose explicit `Autoriser` and `Refuser` buttons.
- A successful approval creates a short in-memory lease (90 seconds is a reasonable default). Serialize prompts so concurrent requests cannot create multiple dialogs.
- Refusal, timeout, AppleScript failure, or expired lease returns `403` before the input subprocess starts.
- Truly invisible operations may pass an explicit `background=1` flag. Never infer background behavior from the caller's intention or from the action name.

## macOS implementation

Use a user-session LaunchAgent and invoke absolute paths:

- `/usr/sbin/screencapture`
- `/usr/bin/osascript`
- `/usr/local/bin/cliclick`

The approval dialog can be implemented with AppleScript through `System Events`:

```applescript
tell application "System Events"
    activate
    display dialog "W.Alter demande le contrôle visible du Mac.\n\nMotif : ..."
        with title "W.Alter — contrôle du Mac"
        buttons {"Refuser", "Autoriser"}
        default button "Refuser"
        giving up after 60
end tell
```

Escape the reason before embedding it in AppleScript and cap its length. Store only an opaque, expiring token in memory; never persist approval tokens.

Use a threaded HTTP server. The request that displays the dialog may wait, but health, recovery, and status requests must remain available while it waits.

## TCC and stale-process recovery

A black Retina capture around 97–110 KB, with the console session active and unlocked, indicates an unusable Screen Recording context. If the Screen Recording entry is already enabled, restart the user LaunchAgent first (`launchctl kickstart -k gui/$(id -u)/<label>`); a stale Python process can retain the old TCC context. Do not reset the whole TCC database as a first response.

After restart, verify all three invariants:

1. `/health` returns `200`.
2. `/control-status` returns `approved=false` by default.
3. `/screenshot` returns a 2880×1800 PNG with a normal non-black payload, typically hundreds of KB or more.

## Deployment and verification

Before replacing a remote script, make a timestamped backup, compile the candidate with `python3 -m py_compile`, install it atomically, and restart the LaunchAgent. Verify the read-only endpoints before testing the prompt. A prompt test must state that no action follows; after the user responds, clear the test lease by restarting the service or waiting for expiry.
