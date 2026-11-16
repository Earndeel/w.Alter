# System prompt slimming / registry progressive disclosure

Session-derived production pattern for reducing Hermes system-prompt bloat without destroying provider prefix-cache economics.

## Problem shape

After tool-result slimming, the remaining prompt bloat may be the `role=system` block itself. In the observed production payload:

- System prompt: ~85.5K chars, ~93% of payload after tool slimming.
- Largest contributors:
  - Project/context instruction files: ~47.5K chars after truncation.
  - Full `<available_skills>` catalog: ~23.3K chars / 234 skill names with many descriptions.
  - Skill mandatory policy was too aggressive and encouraged unnecessary full `skill_view` loads.
- Tool schemas are not part of `role=system`; measure them separately as provider `tools[]` JSON.

## Target layer model

Keep cacheable, byte-stable material early and stable; keep volatile facts late and compact.

1. `STATIC_CORE`
   - Identity and essential operating rules only.
   - No timestamp, model/provider, cwd, host, or session metadata.
   - Compact memory-routing rule, not the entire procedural universe.

2. `STATIC_REGISTRIES`
   - Compact skill/tool registry.
   - Do not render the full skill catalog by default.
   - Keep exact names for critical routing skills.

3. `SEMI_STATIC_PROFILE`
   - USER profile and critical MEMORY facts.
   - Changes rarely; keep compact and non-procedural.

4. `VOLATILE_SESSION`
   - host, cwd, active profile, conversation date, model/provider, session id.
   - Avoid putting this before stable cacheable core if the provider/API permits split prompt parts.

5. `DYNAMIC_CONTEXT`
   - compressed history, Hindsight selections, tool digests, slim raw tail, latest user message.

## Implementation pattern

### Replace full skill catalog with compact registry

Do not inject `<available_skills>` with every skill description. Render something like:

```xml
<skill_registry_compact>
  policy: full catalog intentionally omitted; discover with skills_list/skill_view.
  critical_skills:
    - hermes-agent [autonomous-ai-agents]: ...
    - hermes-context-management [devops]: ...
    - hermes-payload-architecture [devops]: ...
    - hindsight-debug-and-repair [devops]: ...
    - model-id-lookup [devops]: ...
  main_categories:
    - devops: 60 skills (hermes-agent, hermes-context-management, ... +N more)
  compact_shortlist: deterministic small name list
</skill_registry_compact>
```

Keep these critical exact names in the compact registry:

- `hermes-agent`
- `hermes-context-management`
- `hermes-payload-architecture`
- `hindsight-debug-and-repair`
- `model-id-lookup`

### Rewrite skill-loading policy

Use progressive disclosure instead of mandatory broad loading:

- For Hermes config/debug/extension: load `hermes-agent` or the exact matching skill.
- For a known technical task: load the exact skill if identified.
- If several skills may match: use `skills_list` or CLI `hermes skills search <query>` before `skill_view`.
- For analysis, strategy, explanation, or ordinary conversation: do not load a skill unless concrete execution depends on it.
- Do not load multiple large skills without an operational reason.
- If a skill was already loaded in the session: rely on loaded-skill digest/registry, not full reload.

Note: runtime tool names are `skills_list` and `skill_view`; the CLI has `hermes skills search`. Do not invent a runtime `skill_search` tool unless it exists in the active toolset.

### Bound project context files

Large project instruction files can dominate the system prompt even after skill registry slimming. A cache-friendly default cap (e.g. ~12K chars per context file) with a `read_file` recovery pointer is often a better cost/quality tradeoff than scaling the cap up for 1M-token models.

Do not delete the context; head/tail truncate it and include a precise marker telling the agent where to `read_file` for full content.

## Production validation checklist

Capture actual provider request dumps before/after, not just unit tests.

Metrics to report:

- `system` chars/tokens before and after.
- full skill catalog chars vs compact registry chars.
- number of skill names listed in system.
- total prompt tokens, cached tokens, non-cached tokens.
- cache hit on two similar consecutive runs.
- `% by role`: system / user / assistant / tool.
- `role=tool` chars and digest counts, to ensure tool slimming did not regress.
- count of raw skill contents still present in provider payload.
- count of skill dedupe markers.
- separate `tools[]` schema JSON size if tool schemas are a suspected next bottleneck.

Functional checks:

1. Provider accepts payload; no tool-call pairing error.
2. `exact_recall(state_ref)` still retrieves raw tool result from `state.db`.
3. Long `skill_view` content is not reinjected raw on the next turn.
4. Re-loading an already loaded skill produces a digest/dedupe marker, not full content.
5. Raw source in `state.db` remains unchanged.
6. Digests include enough information: tool, id, timestamp, status, summary, key points/paths, `state_ref`.
7. Skill discovery still works through `skills_list`/`skill_view` and, where relevant, CLI `hermes skills search`.

## Example production result

Observed after applying the pattern:

- System prompt: ~85.5K chars to ~33.6K chars, about 60.8% reduction.
- Skill catalog/registry: ~23.3K chars to ~4.5K chars, about 80.8% reduction.
- Skill names listed: 234 to 23.
- Total prompt tokens run 2: ~34K to ~21.8K.
- Cache hit run 2: ~89%, still above an 85% target.
- Tool role stayed under 10%.

Interpretation: a slightly lower cache-hit percentage can still be a win when total prompt size drops sharply and non-cached tokens stay roughly flat.

## Pitfalls

- Do not optimize by removing USER PROFILE or critical MEMORY facts blindly.
- Do not move volatile session data into the static core.
- Do not reintroduce full skill contents in the system prompt.
- Do not confuse system prompt size with provider `tools[]` schema size; they are separate buckets.
- Do not preserve a huge full catalog just to improve cache percentage; optimize total billed/non-cached tokens and quality together.
