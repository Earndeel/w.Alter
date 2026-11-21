# Launch and Focus

Prefer atomic `launch_app` or `open_url` when native launch is available. The action may perform a bounded mechanical wait, inspect process/windows, and return compact AX post-state.

Treat `process_running=true` with `window_ready=false` as two facts, not completion or failure of the user's task. Hermes decides whether to wait, observe elsewhere, focus an existing window, or change strategy.

Use `focus_app`/window targeting after observing actual app, PID, and window evidence. Never invent a target.
