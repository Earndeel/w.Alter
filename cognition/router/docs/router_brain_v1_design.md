# Router Brain V1 — W.Alter / Hermes

Status: dry-run architecture, additive only. No gateway/core hook yet.

## Objective

Router Brain V1 decides, before answering, the cheapest safe execution path for a user turn:

1. intent router — what kind of request is this?
2. model router — which provider/model class should answer?
3. profile router — should W.Alter answer directly or hand off to a Hermes profile such as `coder`?
4. context router — how much memory/history/repo context should be injected?
5. async orchestrator — should this become a background mission with status/ledger?
6. telemetry — record safe routing signals without raw secrets.

## Design constraints

- Additive only: policy + dry-run classifier + smoke tests.
- No gateway integration until route decisions are proven.
- No secrets in policy, telemetry, logs or final reports.
- Do not inject full Hermes context into coder workers.
- Respect current delegation caps: max_concurrent_children=3, max_spawn_depth=1, subagent_auto_approve=false.
- Coder profile remains the execution back-office for code missions.
- Memory retrieval is gated by route; `retrieved` is not automatically `injected`.

## Current routing audit summary

- Main profile model: provider `opencode-go`, model `kimi-k2.6`.
- Main fallback: `openrouter` + `deepseek/deepseek-v4-pro`.
- Main `smart_model_routing`: disabled and empty.
- Main `super_coder_autoroute`: enabled and points to the coder super-stack runner.
- Coder profile `smart_model_routing`: configured with debug/design/review/backend routes.
- Live code issue: `agent.smart_model_routing` is currently absent from the source tree, so tests importing `resolve_turn_route` fail. Router Brain V1 must not depend on that module.
- `delegate_task`: child agents run with `skip_context_files=True` and `skip_memory=True`; context must be explicitly passed in a compact capsule.

## Router Brain V1 route families

### 1. simple.weather

Use when the request is a weather/current lookup.

Decision:
- W.Alter answers directly.
- Toolsets: `web`.
- Memory: off/minimal.
- Context: last user turn only.
- Model: fast/default main model unless policy overrides.

### 2. simple.general

Use for short non-current, non-code, non-sensitive requests.

Decision:
- W.Alter answers directly.
- Toolsets: none or minimal.
- Memory: off/minimal.
- Context: last user turn only.

### 3. research.web

Use for current facts, market/news/docs lookup or source-backed research.

Decision:
- W.Alter answers directly with web tools.
- Memory: sniper/minimal, only if helpful.
- Context: compact.
- Telemetry records source requirement, not raw query.

### 4. multi_step.orchestrator

Use for multi-step operational tasks that are not clearly code.

Decision:
- W.Alter remains orchestrator.
- Can use delegate_task with bounded subagents.
- Max children=3, depth=1.
- Memory: sniper with capped budget.
- Requires final verification before reporting success.

### 5. coding.coder_async

Use for implementation/debug/build/refactor/deploy-ish code tasks.

Decision:
- Route to coder profile / super-coder async runner.
- Context capsule only: goal, repo, task type, constraints, acceptance, verification commands.
- Prefer repo-local memory (`CODER.md`, `.hermes/coder-rules.md`) over global memory.
- Maker/checker split happens inside the coder Work OS.
- No deploy/prod side effect unless explicit user scope exists.

### 6. review.checker

Use for code review/audit/security/review requests.

Decision:
- Route to coder checker/review flow or direct review worker.
- Read-focused tool scope.
- Model preference: Sonnet-class checker when available.
- Output must include verdict, critical issues, important issues, minor issues and verification evidence.

### 7. fallback.default

Use when no route is confident.

Decision:
- W.Alter answers directly with normal configured model.
- Memory: normal/sniper depending on active profile.
- No async orchestration.
- If ambiguity affects side effects, ask one clarifying question.

## Decision JSON contract

Dry-run decisions use this shape:

```json
{
  "schema": "router_brain.v1.decision",
  "route": "coding.coder_async",
  "confidence": 0.86,
  "intent": {
    "family": "coding",
    "name": "implementation",
    "signals": ["keyword:debug", "keyword:repo"]
  },
  "decision": {
    "mode": "coder_super_stack_async",
    "profile": "coder",
    "model": {"provider": null, "model": null, "selection": "inside_coder_profile"},
    "toolsets": ["terminal", "file", "web"],
    "memory": {"mode": "repo_local", "budget_chars": 3000},
    "context": {"capsule": "minimal_task_capsule", "include_history": "none_by_default"},
    "orchestrator": {"enabled": true, "async": true, "max_children": 3, "max_depth": 1, "auto_approve": false}
  },
  "telemetry": {
    "safe": true,
    "query_hash": "...",
    "query_preview_redacted": "...",
    "raw_query_logged": false
  }
}
```

## Telemetry policy

Record only:
- timestamp
- route name
- confidence
- query hash
- redacted/truncated preview
- char/word counts
- matched signal names
- selected profile/mode/model names
- warnings

Never record:
- raw unredacted prompt
- API keys/tokens/passwords
- full environment/config blocks
- credential pool contents

## Integration path after dry-run

1. Keep `~/.hermes/config/router_brain.yaml` as the policy source.
2. Keep `~/.hermes/scripts/router_brain.py` as the deterministic classifier and smoke CLI.
3. Add a native import in Hermes only after tests pass:
   - call `decide_route(user_message, policy)` before normal model call,
   - if `mode=coder_super_stack_async`, spawn the existing coder runner and return ack,
   - if `mode=delegate_task`, build a minimal context capsule and call delegate_task,
   - otherwise continue normal answer with selected context/memory budget.
4. Add a gateway-safe telemetry sink under `~/.hermes/logs/router_brain_decisions.jsonl`.
5. Later: learn route weights from success/failure telemetry, not from vibes.
