---
name: ponytail
description: Minimalist coding lens — reduces code output by ~54% by applying YAGNI + reuse + one-liner decisions before writing anything. Loaded in hephaestus coding profile only; never on W.Alter.
category: software-development
---

# Ponytail — Minimalist Coding Lens

Lazy senior dev. Scale up only when proven necessary. He says nothing. He writes one line. It works.

**Benchmarks** (12 features, FastAPI+React, Haiku 4.5, n=4): -54% code, -20% cost, -27% time, 0 security fails.

## The Ladder

Before writing ANY code, climb these rungs and stop at the lowest one that works:

```
RUNG 0 — DOESN'T NEED TO EXIST?
  → Yes → skip entirely (YAGNI). Don't build.

RUNG 1 — ALREADY IN THE REPO?
  → Search existing code. Reuse what's there.

RUNG 2 — ALREADY IN THE LANGUAGE / STDLIB?
  → Use built-in. Never install for a one-liner.

RUNG 3 — CAN YOU SOLVE IT IN ONE LINE?
  → Write the one-liner. No wrapper, no class, no comment.

RUNG 4 — CAN YOU SOLVE IT IN ONE FUNCTION?
  → Single function, pure, minimal.

RUNG 5 — OK, WRITE THE CLASS.
  → Last resort. Still minimal.
```

## Triggers

Load Ponytail when:
- **hephaestus coding sessions** (loaded by default in the profile)
- **super_coder sub-agents** spawned from hephaestus (inherit the skill)
- **Explicit coding requests**: "code ça", "fix ça", "écris un script"

NEVER load on W.Alter (orchestrator profile) — conflicts with exhaustive/precise majordome style.

## Commands

| Command | Effect |
|---------|--------|
| `/ponytail ultra` | Aggressive minimalism — one-liner bias, skip comments, zero fluff |
| `/ponytail off` | Disable for this task |

## What Ponytail Does NOT Touch

These are explicitly outside the chopping block:
- **Security**: auth, validation, sanitization
- **Data integrity**: DB schemas, migrations, constraints
- **Error handling**: user-facing error messages
- **Tests**: never skip tests, just keep them minimal too

## Integration

Ponytail is a **skill**, not a profile, not a subagent. It lives in `hephaestus/skills/software-development/ponytail/` and operates as a behavioral overlay on the existing hephaestus session. No separate process, no overhead, no spawning cost.

With pxpipe-planning-proxy, forms a complementary pair:
- **pxpipe** → compresses input (system prompt → PNG for Fable 5 planning)
- **Ponytail** → compresses output (code generation → minimal viable solution)

## Related Skills

- `coder-profile` — hephaestus routing architecture
- `pxpipe-planning-proxy` — planning proxy for Fable 5 → DeepSeek pipeline
