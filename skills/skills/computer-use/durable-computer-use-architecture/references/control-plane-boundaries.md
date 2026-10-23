# Control-plane boundaries and remote computer-use operations

- Treat browser, desktop, and remote-control actions as separate trust boundaries because a successful connection does not authorize an irreversible action.
- Prefer a local, loopback-bound or authenticated transport and verify the active endpoint before sending input because a stale proxy can route actions to the wrong session.
- Keep discovery, screenshot, coordinate selection, and click/type execution as distinct steps because each step needs an observable precondition.
- Re-read the current screen after navigation, modal changes, or remote reconnects because cached coordinates become unsafe when the viewport changes.
- Require explicit approval before destructive, external, credential-bearing, or message-sending actions because screen control alone is not consent.
- Preserve the user's existing changes and sessions; isolate experiments in a disposable workspace because cleanup can destroy unrelated work.
- Validate the final user-visible effect, not only transport initialization, because a healthy control channel can still target the wrong window or fail to commit state.
- Record endpoint, session identity, action intent, and verification result without recording secrets because remote-operation traces must remain safe to review.
