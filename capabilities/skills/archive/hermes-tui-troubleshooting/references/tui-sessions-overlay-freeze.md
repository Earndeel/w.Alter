# 2026-07-03 — `/sessions` overlay freeze over cmux/tmux

## User symptom

Monsieur reported that the TUI blocks when opening `/sessions` and that he has to close the cmux window entirely.

## Evidence gathered

- Hermes version: `Hermes Agent v0.17.0 (2026.6.19)`, upstream 1172 commits behind.
- Session DB size/statistics:
  - `state.db`: ~1.5 GB
  - sessions: ~2405
  - messages: ~127k
- Direct `SessionDB.list_sessions_rich()` timings on the live DB:
  - `limit=200, order_by_last_active=True`: ~0.164s
  - `limit=400, order_by_last_active=True`: ~0.190s
- Conclusion: the DB list query was fast enough; the observed freeze was not explained by SQLite query latency.

## Relevant code paths

- Frontend overlay: `ui-tui/src/components/activeSessionSwitcher.tsx`
  - Initial load: `session.active_list` and `session.list` with `limit: 200`.
  - Polling: every ~1.5s with `includeHistory=false`, so it refreshes live status without re-querying resumable DB history.
- Backend RPC handlers: `tui_gateway/server.py`
  - `session.list` around line 4959.
  - `session.active_list` around line 5699.
- Session DB helper: `hermes_state.py`, `SessionDB.list_sessions_rich()` around line 2315.

## Reproduction detail

In a disposable tmux TUI, sending `/sessions` and one `Enter` left the slash-command preview visible. Sending an additional `Enter` executed the command and rendered the Sessions overlay. This matters when reproducing from tmux automation; do not conclude it is hung before pressing Enter enough to actually execute the command.

## Recovery performed

A fresh TUI tmux session was created and the attached client was switched to it:

```bash
REC=hermes-recovery-$(date +%H%M%S)
tmux new-session -d -s "$REC" -x 120 -y 40 "cd /root && HERMES_TUI_FORCE_OSC52=1 bash --norc -c 'hermes --tui --continue --yolo; exec bash'"
sleep 6
tmux switch-client -t "$REC" 2>/dev/null || true
tmux capture-pane -t "$REC" -p | tail -60
```

The observed recovery session was `hermes-recovery-095555`; it became attached and showed the conversation ready. Old processes were not killed.

## Pitfall

Do not encode this as “browser/tools/TUI is broken” or “SQLite session DB is too large.” The durable lesson is the diagnostic split:

1. Measure session DB query latency directly.
2. If DB is fast, treat the problem as TUI overlay/input state.
3. Recover by switching to a fresh tmux TUI without killing existing processes.
