# cmux CLI Patterns

cmux CLI path: `/Applications/cmux.app/Contents/Resources/bin/cmux`

## Discovery Commands

```bash
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"

# List all workspaces
$CMUX list-workspaces
# Output: * workspace:3  ~  [selected]
#           workspace:2  ~
#           workspace:1  ssh -tt walter-ts ...

# List panes in a workspace
$CMUX list-panes --workspace workspace:1
# Output: pane:3  [1 surface]
#         pane:5  [2 surfaces]
#         * pane:7  [2 surfaces]  [focused]

# List surfaces in a pane
$CMUX list-pane-surfaces --workspace workspace:1 --pane pane:5
# Output: surface:5
#         surface:7
```

## Read + Send Commands

```bash
# Read screen content (for detecting broken pipes, dead prompts, etc.)
$CMUX read-screen --workspace workspace:1 --surface surface:3 --lines 5

# Send text to a surface
$CMUX send --workspace workspace:1 --surface surface:3 "ls -la"

# Send a key (enter, tab, etc.)
$CMUX send-key --workspace workspace:1 --surface surface:3 "enter"
```

## Scripted Multi-Session Scanning Pattern

```bash
for ws in $($CMUX list-workspaces 2>/dev/null | grep -o "workspace:[0-9]*"); do
    for pane in $($CMUX list-panes --workspace "$ws" 2>/dev/null | grep -o "pane:[0-9]*"); do
        for surface in $($CMUX list-pane-surfaces --workspace "$ws" --pane "$pane" 2>/dev/null | grep -o "surface:[0-9]*"); do
            SCREEN=$($CMUX read-screen --workspace "$ws" --surface "$surface" --lines 5 2>/dev/null)
            # Process SCREEN content...
        done
    done
done
```

## Common Surface States

| Screen content | State | Action |
|---|---|---|
| `Broken pipe` / `Connection.*closed` | Dead SSH | Reconnect |
| `user@host ~ %` (local prompt, no SSH) | Dead session | Reconnect |
| `No such file` / `command not found` | Bad command path | Fix command |
| `Last login:` | Fresh SSH session | OK |
| `❯ Ask me anything` / `❯ Try` | Active hermes TUI | OK |

## Pitfalls

- **Ctrl+C via send**: `printf "\x03"` works, but `\003` is interpreted literally by zsh. Always use `CTRL_C=$(printf "\x03")` then `$CMUX send ... "$CTRL_C"`.
- **`~` expansion**: When sending SSH commands via `cmux send`, `~` expands locally (on Mac). Quote the remote command: `ssh walter-ts "bash ~/bin/script"` not `ssh walter-ts bash ~/bin/script`.
- **Workspace-specific commands**: Different workspaces may run different commands (e.g., workspace:1 = hermes, workspace:2/3 = plain shells). Detect which workspace and use the appropriate reconnect command.
- **`read-screen` returns terminal escape codes**: Mouse events, ANSI codes, etc. pipe through. Use `grep` with `-i` for pattern matching, not exact string comparison.
- **`cmux list` is not a valid command**: Use `list-workspaces`, `list-panes`, `list-pane-surfaces` separately.
- **`respawn-pane` exists**: Can restart a pane with a new command, but doesn't preserve layout. Reconnect via `send` is more transparent.
