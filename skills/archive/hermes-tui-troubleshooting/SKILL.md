---
name: hermes-tui-troubleshooting
description: Diagnose and recover Hermes TUI freezes, overlay/input stalls, cmux/tmux attachment issues, and TUI gateway session problems without killing user processes.
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, troubleshooting, tmux, cmux, sessions, ink, react]
    related_skills: [hermes-agent, hermes-session-db, hermes-tui-customization, ssh-tmux-persistence]
---

# Hermes TUI Troubleshooting

Use this skill when Monsieur reports that the Hermes TUI is stuck, not accepting input, frozen inside an overlay such as `/sessions`, or requires closing a cmux/tmux window.

## Operating rule

Do **not** jump to `pkill`, `killall`, or broad process termination. Monsieur prefers preserving live processes. First create a safe recovery path, then inspect the stuck process if needed. Barbarism is easy; diagnosis has better tailoring.

## Fast triage

1. Identify whether the TUI is running directly, inside server-side tmux, and/or reached through cmux:
   ```bash
   tmux list-sessions -F '#{session_name} attached=#{session_attached}' 2>&1
   tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} pid=#{pane_pid} tty=#{pane_tty} cmd=#{pane_current_command}' 2>&1
   ps -eo pid,ppid,tty,stat,etime,%cpu,%mem,cmd | grep -E 'hermes --tui|ui-tui/dist/entry|tui_gateway.entry|slash_worker' | grep -v grep
   ```

2. If the report mentions `/sessions`, test whether the session database is actually slow before blaming SQLite:
   ```bash
   hermes sessions stats
   python3 - <<'PY'
   import sys, time
   from pathlib import Path
   sys.path.insert(0, '/root/.hermes/hermes-agent')
   from hermes_state import SessionDB
   db = SessionDB(Path('/root/.hermes/state.db'))
   for kwargs in [
       dict(source=None, limit=200, order_by_last_active=True),
       dict(source=None, limit=400, order_by_last_active=True),
   ]:
       t = time.time(); rows = db.list_sessions_rich(**kwargs)
       print(kwargs, len(rows), f'{time.time()-t:.3f}s')
   PY
   ```

3. Check disk/memory/WAL only as supporting evidence:
   ```bash
   du -h /root/.hermes/state.db* 2>/dev/null
   df -h /root/.hermes | tail -1
   free -h
   ```

## Safe recovery pattern

When the user-facing cmux/tmux client is stuck, start a fresh TUI in a new server-side tmux session and switch the attached client to it. This restores control without destroying the old process:

```bash
REC=hermes-recovery-$(date +%H%M%S)
tmux new-session -d -s "$REC" -x 120 -y 40 "cd /root && HERMES_TUI_FORCE_OSC52=1 bash --norc -c 'hermes --tui --continue --yolo; exec bash'"
sleep 6
tmux switch-client -t "$REC" 2>/dev/null || true
tmux capture-pane -t "$REC" -p | tail -60
```

Report the new session name to Monsieur and explicitly say whether old processes were preserved.

## `/sessions` overlay investigation

The TUI `/sessions` panel is rendered by `ui-tui/src/components/activeSessionSwitcher.tsx` and calls:

- `session.active_list` — live TUI sessions from `tui_gateway/server.py`.
- `session.list` — resumable history, currently loaded around `limit: 200`.

Important diagnostic distinction:

- If `SessionDB.list_sessions_rich(limit=200, order_by_last_active=True)` is slow or locks, investigate SQLite/session DB.
- If the DB call is fast but the overlay remains visible and keys like Escape/Ctrl-C/text do not close or interact, suspect Ink/useInput focus, overlay key handling, or frontend/backend event state rather than DB size.

## React rendering crashes (error #185, #31, etc.)

The TUI is built with React (Ink). When React hits internal guardrails — most commonly the 50-nested-update limit — it throws a minified error that freezes the UI. See `references/react-185-useLayoutEffect-loop.md` for the detailed fix pattern from `useVirtualHistory.ts`.

### Error #185: "Maximum update depth exceeded"

**Signature:** TUI freezes during scroll, prints `Minified React error #185` with stack `getRootForUpdatedFiber → enqueueConcurrentHookUpdate → dispatchSetState`.

**Root cause:** `useLayoutEffect` measuring DOM heights and calling `setState` in the same synchronous render pass → infinite loop → React's 50-update guardrail.

**Fix pattern:** Cap consecutive state updates with a `useRef` counter, reset the gate when the effective range changes (new content, not feed-forward artifact). Detailed code and TDZ pitfall in the reference file.

**Verification:**
```bash
cd ui-tui && npx vitest run src/__tests__/useVirtualHistoryHeights.test.ts src/__tests__/virtualHistoryClamp.test.ts src/__tests__/virtualHistoryOffsetCache.test.ts
```

## Reproduction in a disposable tmux session

```bash
S=tui-sessions-repro-$(date +%H%M%S)
tmux new-session -d -s "$S" -x 120 -y 40 'cd /root && hermes --tui --yolo'
sleep 6
tmux send-keys -t "$S" '/sessions' Enter
sleep 2
# Depending on TUI state, a second Enter may be needed after slash-command preview appears.
tmux send-keys -t "$S" Enter
sleep 3
tmux capture-pane -t "$S" -p | tail -80
# Clean up only the disposable repro session, not the user's live sessions.
tmux kill-session -t "$S" 2>/dev/null || true
```

## Version check

If Hermes reports that it is many commits behind upstream, recommend `hermes update` before deep patching TUI overlay/input bugs. This is especially true for Ink/React TUI issues where upstream may have already fixed event handling.

## Session note

See `references/tui-sessions-overlay-freeze.md` for the observed `/sessions` freeze recovery pattern and concrete evidence from the 2026-07-03 session.
