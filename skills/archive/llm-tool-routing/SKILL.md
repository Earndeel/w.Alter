---
name: llm-tool-routing
description: Use when an LLM must choose a deferred or plugin tool.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [orchestration, tool-routing, plugins, tool-search, prompt-cache]
    related_skills: [hermes-agent, hermes-payload-architecture, universal-web-extraction-router]
---

# LLM Tool Routing

## Overview

Use this skill for architectures where a capable orchestrator LLM selects a
high-level plugin or façade tool and that tool delegates to lower-level
adapters. The orchestrator should understand the user's intent and practical
complexity; the façade should expose a small structured contract; the adapter
router should execute, validate, and escalate. Do not duplicate the
orchestrator's semantic reasoning inside every backend router.

This pattern is especially important in Hermes, where plugin tools may be
progressively deferred behind `tool_search` to protect prompt-cache size.

## When to Use

- A new plugin tool should supersede direct calls to several backend tools.
- A model must choose between a façade and its implementation adapters.
- A deferred tool is present in the catalog but is not being selected.
- Two skills describe overlapping routing rules and may cause backend bypasses.
- A tool works when explicitly named but not in a fresh, natural-language session.

Do not use this skill to add a second LLM planner merely because a backend
fallback chain is imperfect. First determine whether the orchestrator already
produces a sufficient semantic contract.

## Responsibility Boundary

| Layer | Owns | Must not own |
|---|---|---|
| Orchestrator LLM | User intent, task class, practical complexity, high-level tool choice, semantic request contract | Backend-specific mechanics and adapter selection |
| Skill / system guidance | Trigger conditions, precedence, exclusions, discovery instructions | Runtime extraction or validation |
| Façade tool schema | Name, affordance, parameters, constraints, success semantics | Long implementation documentation |
| Backend router | Replay hints, backend order, route selection, fallback, timeouts | Re-interpreting the user's full natural-language intent |
| Semantic validator | Required fields, record count, usable-result gate, evidence | Choosing an unrelated user-facing workflow |

The façade may receive an `objective` for traceability, but a field contract such
as `expected_fields` and `required_fields` must drive deterministic execution.
If `objective` is not wired into routing logic, describe it honestly as context
or result metadata; do not imply that it changes backend selection.

## Designing the Façade Schema

Keep the tool description short, explicit, and trigger-oriented. It should say:

1. When to use the façade.
2. What class of result it produces.
3. Which inputs form the semantic contract.
4. What counts as failure even when the transport succeeds.
5. Which modes are normal operation versus diagnostics.

A good description names the user-facing task class (for example, structured
records, prices, listings, or availability) and states that the façade chooses
its backend automatically. It does not need to enumerate every internal
adapter or reproduce the skill.

Parameter descriptions should make the model's next action unambiguous:

- `url` or target: the known source;
- `expected_fields`: canonical output names mapped to source aliases;
- `required_fields`: fields that must be present;
- `min_records`: minimum usable result count;
- `profile`: a known site journey when one exists;
- `mode`: `auto` for normal operation, explicit modes for diagnostics.

Do not expose low-level adapters as the normal model path merely because they
are individually callable. If a façade exists, backend names belong in
observability and diagnostics, not in the model's decision burden.

## Progressive Tool Discovery

Tool availability has two distinct states:

1. The plugin is registered and appears in the full tool catalog.
2. The plugin schema is deferred from the current prompt and must be loaded.

When a façade is deferred, the correct sequence is:

```text
tool_search("<façade name or capability>")
tool_describe(<façade name>)
tool_call(<façade name>, structured arguments)
```

A schema description improves relevance but does not force priority. A skill or
system instruction must establish the routing rule, for example:

```text
Known URL + structured extraction → use the façade.
No known URL → use the discovery/search branch.
Visual interaction, login, or CAPTCHA → use the interactive browser branch.
```

Avoid hardcoding names of tools from unrelated toolsets in a generic schema;
keep cross-tool routing in the skill or dynamic tool-definition layer where the
availability context is known.

## Skill Precedence and Overlap

A generic skill can silently defeat a more specific façade. For example, a
generic rule such as “explicit URL → call the Scrapling adapter” bypasses a
first-class Walter façade even when the façade is registered and valid.

When overlap exists:

1. The domain-specific façade skill must explicitly supersede the generic rule
   for its covered request class.
2. The generic skill must delegate to the façade instead of naming a backend.
3. Verify both a fresh default session and a session with the specific skill
   preloaded.
4. Inspect actual tool-call names; a correct final answer obtained through the
   wrong backend does not validate the architecture.

See `references/walter-browse-selection-test.md` for a concrete reproduction and
interpretation.

## Verification Workflow

1. **Define the natural request.** Use a known URL and a small structured task;
   do not mention the façade name in the baseline prompt.
2. **Run a fresh Hermes process.** Tool schemas and skill activation are cached
   per session; an existing chat is not a valid discovery test.
3. **Inspect the trace.** Record the first skill loaded, `tool_search` /
   `tool_describe` calls, the final façade call, arguments, route, and semantic
   result. Do not infer tool choice from the final prose alone.
4. **Run a controlled comparison.** Preload the intended façade skill and repeat
   the same natural request.
5. **Classify the outcome:**
   - façade selected in both runs: discovery and precedence are sound;
   - façade selected only when preloaded: orchestrator capability is sound, but
     activation or skill precedence is wrong;
   - façade selected but fields are poor: improve schema/skill contract;
   - façade returns weak data: fix router validation/adapters, not prompting.

Completion means the trace shows both the intended high-level tool and a
semantically valid result, or the remaining failure is assigned to the correct
layer.

## Common Pitfalls

1. **Adding a second planner too early.** If the orchestrator can already turn
   intent into canonical fields, keep the router deterministic and observable.
2. **Confusing correct data with correct routing.** Direct Scrapling may return a
   valid answer while proving that the façade-selection contract is bypassed.
3. **Making the schema encyclopedic.** Long adapter descriptions spend prompt
   tokens and dilute the trigger. Put procedures in the skill and details in a
   reference file.
4. **Assuming registration means visibility.** A deferred plugin may be present
   in the catalog but absent from the model's active schema.
5. **Leaving competing generic rules active.** Specific façade routing must win
   over a generic “URL → backend” shortcut.
6. **Treating `mode=auto` as a model-planning failure.** The orchestrator chooses
   the façade; the façade's router chooses the backend in auto mode.

## Verification Checklist

- [ ] The orchestrator can identify the request class without the façade name in the prompt.
- [ ] The model produces a complete semantic contract, including canonical and required fields.
- [ ] A fresh session's trace shows the intended façade, not only a successful backend call.
- [ ] Deferred discovery uses `tool_search` / `tool_describe` before `tool_call` when needed.
- [ ] The façade uses normal automatic mode and returns a semantic success gate.
- [ ] Generic overlapping skills delegate to the façade instead of bypassing it.
- [ ] No second LLM planner was added without measured evidence that the orchestrator contract is insufficient.
