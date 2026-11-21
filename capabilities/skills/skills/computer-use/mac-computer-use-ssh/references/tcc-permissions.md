# macOS TCC Permissions for Computer Use

## What is TCC?
macOS Transparency, Consent, and Control (TCC) requires explicit user permission for screen capture and input simulation. Each process binary needs its own permission grant.

## Required Permissions

### Screen Recording (for `screencapture`)
- **System Settings** → Privacy & Security → Screen Capture
- **Must add**: The process that runs `screencapture`. When using SSH, this is the SSH session's parent app (cmux, Terminal, iTerm).
- **Symptom without**: `screencapture` returns a black PNG (~97KB for 2880×1800). A real screenshot is 300KB-1.5MB.
- **Adding CLI tools**: Click "+" → ⌘Cmd+⇧Shift+G → type `/usr/bin/python3` or path to terminal app.

### Accessibility (for `cliclick` and `osascript`)
- **System Settings** → Privacy & Security → Accessibility
- **Must add**: `/usr/local/bin/cliclick`
- **Symptom without**: Click commands silently succeed but nothing happens on screen.

## How to Grant via SSH (guide user)

Cannot be automated — user must click through System Settings manually. Guide them:

1. Open: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"`
2. Click "+" → ⌘Cmd+⇧Shift+G → type `/usr/bin/python3` → Select
3. Then: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`
4. Click "+" → ⌘Cmd+⇧Shift+G → type `/usr/local/bin/cliclick` → Select

## Verification

After granting permissions:
```bash
# Screenshot should be >200KB
curl -s http://localhost:18765/screenshot -o /tmp/test.png && ls -la /tmp/test.png

# Click should have visible effect
curl -s "http://localhost:18765/click?x=1440&y=900"
```

## Pitfalls

- **Permission per process**: LaunchAgent's Python ≠ cmux ≠ Terminal. Each needs separate Screen Recording permission if they run `screencapture`.
- **Permission change requires restart**: After granting, the process may need to be restarted.
- **SIP-protected TCC DB**: Cannot query `~/Library/Application Support/com.apple.TCC/TCC.db` from SSH (SIP blocks it). Only way to verify is to test.
- **`launchctl asuser` fails from SSH**: "Operation not permitted" — can't switch to GUI audit session from SSH. The LaunchAgent approach (running natively in the GUI session) is the workaround.
