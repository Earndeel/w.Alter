# walter-soul — detailed guide

## Purpose
Give every runtime the same identity of W.Alter, the same rules and the same profile of {{owner.address}}. The
software is neutral; the identity belongs to the instance (`@instance/soul`, versioned in git).

## How to use it
`walter_profile()` returns {{owner.address}}'s profile (USER.md), W.Alter's identity and rules rendered for a neutral
runtime, and the critical memory (MEMORY.md). Short; load it at the start of a session when the way to answer or
their preferences matter and the profile is not already in the prompt.

## Organisation
| Part | Role |
|---|---|
| Renderer `walter-soul` | Composes identity + rules + runtime adapters; `render`, `sync`, `check`, `init` |
| `runtimes/*.md` | Neutral adapters per runtime (Claude Code, Codex, agent CLI) |
| Instance `soul/{identity,rules}.md`, `soul/runtimes/` | The identity itself and the instance's additions; a commit runs `walter-soul sync` |
| Targets (`@instance/config/soul/targets.toml`) | The engine's Soul and conduct files, the Claude Code / Codex W.Alter profiles, MCP `walter_profile` |

## Rules and limits
- Rendered files are generated: edit the instance's Soul and commit, never the rendered file. `walter-soul check`
  detects hand edits.
- The engine reads its Soul and conduct files at each turn: an edit reaches an open session at its next turn.
- An external agent session opened outside the W.Alter profiles is in technician mode.
