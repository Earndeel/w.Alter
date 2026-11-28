# Walter Computer — detailed guide

## Purpose
Observe and manipulate one of {{owner.address}}'s devices (their Mac) through safe atomic actions, for tasks that
exist only in a native application. The agent keeps the goal, the plan and the decisions; the module chooses the
target, applies the presence and interruption policy, checks the captures and recovers cleanly.

## How to use it
`computer_use(session_id, action, arguments)` with one atomic action: `list_apps`, `list_windows`, `device_context`,
`capture`, `click`, `type`, `key`, `scroll`, `drag`, `set_value`, `focus_app`, `launch_app`, `open_url`,
`click_visual_ref`, `targeted_verify`, `wait`, `close`.
1. Capture the exact application before any input.
2. Check the effect (`targeted_verify` or a new capture) after each action that matters.
3. `close` at the end of the task.

## Organisation
| Part | Role |
|---|---|
| `walter_computer.policy`, `runtime`, `observer`, `types` | Independent core: policy, visual reference guard, observations |
| `operator`, `driver`, `transport` | Sessions (16 max, expire after 15 min), CuaDriver port; one lock per device |
| Device node (`~/walter-computer-use` on the device) | SSH transport to the enrolled device |
| Configuration | `config/config.json` (no device); the real device is declared in the instance |

## Interfaces
| Need | MCP | Python |
|---|---|---|
| Atomic actions | `computer_use` (local stdio client only) | `OperatorSessions.call` |

## Rules and limits
- Permissions come from the server policy (`computer-policy.json`); an argument cannot grant any.
- `device_busy` if another call holds the device; vision requires a configured sensor.
- Not available to a remote (HTTP) MCP client; unavailable while the device is offline.
