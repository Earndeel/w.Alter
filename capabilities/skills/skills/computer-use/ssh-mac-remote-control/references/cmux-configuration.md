# cmux Configuration

cmux (manaflow-ai/cmux) is a macOS terminal multiplexer. Config lives at `~/.config/cmux/` on the Mac.

## Config Files

| File | Purpose |
|---|---|
| `~/.config/cmux/cmux.json` | Main config (may have shell prefix — see pitfall below) |
| `~/.config/cmux/settings.json` | Secondary config (clean JSON) |

Both files have overlapping keys. When changing settings, update **both** files.

**Pitfall:** `cmux.json` can contain shell commands at the start (e.g. `mkdir -p ~/.config/cmux\ncat > ...`). Python `json.load()` will fail. Use `sed` for in-place edits:

```bash
ssh lucasjouvencon@100.127.150.1 "cd ~/.config/cmux && sed -i '' \
  's/\"paneFlash\": true/\"paneFlash\": false/g; s/\"unreadPaneRing\": true/\"unreadPaneRing\": false/g' \
  cmux.json settings.json"
```

## Notification Settings

Section: `notifications` in both config files.

```json
"notifications": {
    "dockBadge": true,        // Badge on dock icon
    "paneFlash": true,        // Blue border flash on pane ← THE ANNOYING ONE
    "showInMenuBar": true,    // Menu bar indicator
    "sound": "none",          // "none" or "default"
    "unreadPaneRing": true    // Ring indicator on pane ← ALSO ANNOYING
}
```

**To disable blue pane border while keeping notifications:**
- Set `paneFlash: false` and `unreadPaneRing: false`
- Keep `dockBadge: true` and `showInMenuBar: true`
- After editing, restart cmux (no CLI reload command available — `cmux` binary is inside the .app bundle at `/Applications/cmux.app/Contents/Resources/bin/cmux`, not in PATH)

## Relationship with tmux Notifications

The `cmux-notify` script on the VPS sends OSC 777 via tmux `allow-passthrough`. This is **independent** of tmux's bell/activity system. Disabling `visual-bell`, `visual-activity`, `monitor-activity`, or `bell-action` in tmux.conf does NOT affect cmux notifications — the OSC 777 bypasses tmux entirely.

The blue border comes from cmux's own `paneFlash` setting, not from tmux.

## Other Useful Settings

```json
"app": {
    "reorderOnNotification": false,  // Don't reorder workspaces on notify
    "focusPaneOnFirstClick": true
},
"workspaceColors": {
    "indicatorStyle": "border",      // How workspace indicators appear
    "notificationBadgeColor": "#FFFFFF"
}
```

## Applying Changes

No `cmux reload-config` CLI exists in PATH. The binary is at:
```
/Applications/cmux.app/Contents/Resources/bin/cmux
```

Options:
1. Restart cmux app
2. Use the full path: `/Applications/cmux.app/Contents/Resources/bin/cmux reload-config`
3. Open cmux preferences and re-save
