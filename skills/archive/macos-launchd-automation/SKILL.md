---
name: macos-launchd-automation
description: macOS LaunchAgent automation reliability patterns — minimal environment, TCC-protected paths, SSH automation, watchdog verification, and non-destructive service updates.
version: 1.0.0
author: W.Alter
---

# macOS Launchd Automation

## When to Use

Use this skill when debugging or designing macOS automation launched by `launchd`, especially:

- LaunchAgents that run shell scripts, watchdogs, SSH commands, cmux/tmux attachers, or background helpers.
- Commands that work interactively but fail when run by `launchd`.
- Reconnect loops that restart sessions repeatedly even though the underlying service is healthy.
- Automation involving files under Desktop/Documents/Downloads or other TCC-protected locations.

## Core Principle

Do not assume the interactive shell environment matches `launchd`. A LaunchAgent has a minimal environment, different PATH behavior, and may hit macOS privacy restrictions that do not appear in an interactive Terminal.

## Debugging Sequence

1. Inspect the LaunchAgent script and its log output first.
2. Run the exact script manually.
3. Re-run it under a minimal environment similar to `launchd`:
   - preserve only `HOME`, `USER`, `LOGNAME`, and a conservative system `PATH`.
4. Replace fragile relative paths with absolute paths.
5. Move automation identity/config files out of Desktop/Documents/Downloads into standard per-user config directories.
6. Validate script syntax before waiting for the next launchd tick.
7. Wait one real LaunchAgent interval and confirm the log shows a healthy no-op/no-reconnect result.

## SSH Automation Pattern

- Prefer direct tailnet host aliases over local tunnel aliases when the remote host is reachable directly.
- Avoid using a local forwarded port as the health check if the actual remote route can be tested directly.
- Keep identity files in the user's standard SSH directory; Desktop/Documents can fail under TCC when launched non-interactively.
- Use `BatchMode=yes`, short `ConnectTimeout`, and explicit config paths in health checks.
- Do not store specific addresses, keys, or credentials in the skill. Put secrets in vault and host-specific details in the active environment or a protected ops reference.

## Watchdog Pitfalls

- A blank tmux/cmux pane is not proof that the session is dead. Check real process/session state before restarting.
- Avoid broad process killing. Prefer patching the LaunchAgent/script and letting the watchdog converge.
- A reconnect loop every fixed interval usually means the health check is wrong, not that the service needs more restarts.

## Foreground-control approval for Mac automation

When a LaunchAgent-backed Computer Use service can visibly move the user's cursor, steal focus, or control the screen, observation and control must be separate. Health checks and screenshots stay prompt-free; foreground input obtains a short native approval lease first (explicit **Autoriser / Refuser**, serialized prompts, expiry such as 90 seconds). A refusal or timeout must return before invoking `cliclick`/`osascript`. Genuinely invisible operations may opt out only with an explicit `background=1` contract. Use a threaded server so health and recovery remain available while the dialog waits. See `references/foreground-control-approval.md` for the implementation and verification pattern.

## Verification Checklist

- Manual command succeeds.
- Minimal-environment command succeeds.
- Script syntax check succeeds.
- For long-lived sockets, verify the idle lifetime beyond the bounded connect timeout; clear that timeout once the upstream connection is established.
- After a targeted LaunchAgent change, re-check sibling jobs and listeners rather than trusting the launchctl command alone.
- One real LaunchAgent interval passes without unnecessary restart.
- Log shows a healthy no-op/reconnected-zero style result.

## Related

This complements SSH-specific skills. If an SSH skill cannot be patched because its existing contents trigger security scanners, capture generic launchd/TCC lessons here instead of forcing unsafe writes.
