# Natural Front-Door Enforcement

## Purpose

Use this reference when a high-level façade exists but a fresh Hermes session
still selects low-level tools, transport recipes, or legacy skills. It records
the validated reasoning from Lot 1.2 without making the session narrative itself
the class-level skill.

## Root-cause checklist

- **Schema drift:** Does the tool description still say `capture first` even
  though `goal` is available?
- **Prompt drift:** Does system guidance teach primitives as the preferred path?
- **Discovery drift:** Are legacy skills still visible in the normal skill index?
- **Surface drift:** Does `skills_list` expose entries hidden from the system
  prompt, or vice versa?
- **History drift:** Does generic session-search guidance allow old SSH/CLI
  recipes to become execution instructions?
- **Authority drift:** Does a legacy preference override the latest explicit
  user target?
- **Runtime drift:** Can the goal router click a plausible AX node when the
  requested semantic target is absent?

## Preferred metadata pattern

For a legacy or fallback skill that must remain available for maintenance but
not normal selection:

```yaml
metadata:
  hermes:
    fallback_for_tools: [computer_use]
```

This is an offer-time condition, not a deletion or an access-control boundary:
explicit `skill_view`, a direct preload, and a maintenance request remain
valid. The condition must be applied consistently to the system-prompt index,
`skills_list`, slash/autocomplete discovery, and plugin metadata.

## Natural smoke-test protocol

Use a completely new Hermes process/session. Do not put the expected tool name
in the user prompt. For a native Mac request, record at minimum:

```text
user prompt
→ first model-facing tool call and arguments
→ loaded skills
→ terminal / SSH / session_search / raw driver calls
→ internal backend routes
→ screenshots and vision calls
→ latency and token fields
→ final status
```

A valid negative result is evidence: if the current AX state contains only
empty-feed markers such as `Try searching to get started` and no real video
candidate, the router should return `needs_user_input` with
`completion_known=true`, zero mutation, zero arbitrary reload/wait, and zero
vision when AX is sufficient.

## Interpretation

- `goal` selected naturally: front-door selection works for that request.
- `goal` selected only when named in the prompt: schema/runtime exists, but
  orchestration guidance or discovery precedence is insufficient.
- Legacy skill loaded: normal discovery filtering is incomplete even if the
  legacy skill says not to use itself.
- Terminal/SSH/history used: the current supported route is not authoritative
  enough in the model-facing prompt.
- Wrong named app despite an old preference: add an explicit latest-user-message
  precedence rule and a regression test.
- No target followed by click/reload/vision: fix runtime semantic candidate
  matching; do not merely add another prompt warning.

Never present an untested natural smoke test as proof of enforcement. A green
unit test for the backend is not evidence that the model selected the façade.
