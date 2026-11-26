# Walter Computer

**Role.** Observe and manipulate one of {{owner.address}}'s devices (their Mac) through safe atomic actions, for what
exists only in a native application. The agent keeps the goal and the plan; the module chooses the target, checks
the captures and recovers cleanly.

**Organisation.** A policy and observation core, sessions per client (one lock per device), a transport to the
enrolled device.

**Tool**: `computer_use(session_id, action, arguments)` — `list_apps`, `list_windows`, `device_context`, `capture`,
`click`, `type`, `key`, `scroll`, `drag`, `set_value`, `focus_app`, `launch_app`, `open_url`, `targeted_verify`,
`wait`, `close`.
1. Capture the exact application before any input. 2. Check the effect of actions that matter. 3. `close` at the end.

**Rules**: permissions come from the server policy, never from arguments; local stdio client only.
