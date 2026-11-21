# MEMORY.md Routing Guardrails

## Purpose

`MEMORY.md` is injected into future turns, so it must not become the default storage sink. Treat it as a near-empty critical-facts buffer, not an operations log.

## Canonical Routing

- `USER.md`: stable user profile, preferences, communication style, pet peeves, interaction constraints.
- `SOUL.md`: W.Alter identity, tone, durable operating principles.
- `EVOLUTION.md` or Hindsight: lessons learned, historical context, investigations, session outcomes.
- Skills: procedures, commands, infrastructure architecture, APIs, workflows, troubleshooting playbooks.
- Vault: credentials, accounts, tokens, API keys, passwords, secret locations.
- `MEMORY.md`: tiny critical operational facts only — facts whose absence would likely cause an error on nearly every turn.

## Tool-level Guard Pattern

When Hermes keeps dumping into `MEMORY.md` or `USER.md`, add enforcement where the write happens, not only in prose instructions:

1. Add a routing classifier before memory writes are applied.
2. For `target='memory'`, reject entries that look like credentials, procedures, infrastructure, historical task state, URLs, ports, commands, or long narratives.
3. Do not assume guarding `target='memory'` covers all persistence: `target='user'` writes to `USER.md` and can still persist style/workflow corrections automatically.
4. Return a clear error telling the agent where the item belongs instead: `skill_manage`, Hindsight, USER.md, SOUL.md, or vault.
5. Tighten the `memory` tool schema description so the model sees the routing hierarchy before calling the tool.
6. Keep a small policy line inside `MEMORY.md` itself because it is always injected.
7. Check the memory write-approval setting; when enabled, memory and user-profile writes are staged for review instead of committed directly.
8. Verify with an isolated test home: one infra/procedure write must fail; one `target='user'` preference write must pass when approval is off and stage when approval is on.

## Verification Recipe

Expected behavior:

- `memory(add, target='memory', content='Procedure: ... ssh ... docker ...')` returns `success=false` and a refusal mentioning `MEMORY.md` routing.
- `memory(add, target='user', content='User prefers concise French answers.')` returns `success=true`.
- `py_compile tools/memory_tool.py` passes after editing the tool.

## Pitfall

Do not encode environment-specific coordinates, secrets, ports, or one-off incident details in this reference. The durable lesson is the routing/enforcement pattern, not the incident that exposed it.
